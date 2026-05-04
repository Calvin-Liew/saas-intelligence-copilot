from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .data_loader import load_processed_or_demo
from .enrichment import search_open_source_alternatives
from .llm import LLMResult, generate_answer
from .normalizer import normalize_name, split_terms, to_bool
from .retrieval import apply_product_filters, match_product_names, search_rows
from .scoring import (
    extract_price_ceiling,
    feature_display_name,
    feature_columns,
    is_review_derived_feature,
    map_required_features,
    score_products,
)


@dataclass
class AnalysisResult:
    answer: str
    source_notice: str
    recommended_tools: pd.DataFrame
    comparison_table: pd.DataFrame
    review_themes: pd.DataFrame
    evidence_snippets: pd.DataFrame
    enterprise_metadata: pd.DataFrame
    vendor_metadata: pd.DataFrame
    open_source_alternatives: pd.DataFrame
    required_features: list[str]
    ranking_explanation: list[str]
    risks: list[str]
    follow_up_questions: list[str]
    confidence: str
    llm_provider: str
    llm_model: str
    llm_status: str
    llm_warning: str


def run_analysis(
    query: str,
    category: str | None = "All",
    max_monthly_price: float | None = None,
    required_features_text: str | None = "",
    compare_tools_text: str | None = "",
    top_k: int = 5,
    use_llm: bool = True,
) -> AnalysisResult:
    products, reviews, source_notice = load_processed_or_demo()
    features = feature_columns(products)
    inferred_price_ceiling = extract_price_ceiling(query)
    price_ceiling = max_monthly_price if max_monthly_price is not None else inferred_price_ceiling

    selected = _select_products(
        products=products,
        query=query,
        category=category,
        max_monthly_price=price_ceiling,
        compare_tools_text=compare_tools_text,
        top_k=max(top_k, 5),
    )
    required_features = map_required_features(
        query,
        required_features_text,
        features,
        category=category,
        candidate_products=selected,
    )

    if selected.empty:
        return _empty_result(source_notice, required_features)

    scored = score_products(
        selected,
        required_features=required_features,
        query=query,
        category=category,
        max_monthly_price=price_ceiling,
    ).head(top_k)

    evidence = _retrieve_review_evidence(reviews, scored, query, max_snippets=max(6, top_k * 2))
    review_themes = _review_themes(evidence)
    comparison_table = _comparison_table(scored, required_features)
    recommended_tools = _recommended_table(scored)
    enterprise_metadata = _enterprise_metadata(scored)
    vendor_metadata = _vendor_metadata(scored)
    open_source_alternatives = search_open_source_alternatives(query, top_k=max(5, min(top_k, 8)))
    ranking_explanation = _ranking_explanation(scored, evidence, required_features)
    risks = _risks(scored, required_features, source_notice)
    follow_ups = _follow_ups(required_features, price_ceiling)
    confidence = _confidence(scored, evidence, required_features)

    grounded_answer = _template_answer(
        query=query,
        scored=scored,
        evidence=evidence,
        required_features=required_features,
        ranking_explanation=ranking_explanation,
        risks=risks,
        follow_ups=follow_ups,
        confidence=confidence,
        source_notice=source_notice,
        enterprise_metadata=enterprise_metadata,
        vendor_metadata=vendor_metadata,
        open_source_alternatives=open_source_alternatives,
    )
    context = _context_for_llm(
        scored,
        evidence,
        required_features,
        risks,
        confidence,
        enterprise_metadata=enterprise_metadata,
        vendor_metadata=vendor_metadata,
        open_source_alternatives=open_source_alternatives,
    )
    llm_result = (
        generate_answer(query=query, context=context, grounded_draft=grounded_answer)
        if use_llm
        else LLMResult(
            content=None,
            provider="template",
            model="grounded-template",
            status="disabled",
            warning="LLM generation is disabled.",
        )
    )
    answer = llm_result.content or grounded_answer

    return AnalysisResult(
        answer=answer,
        source_notice=source_notice,
        recommended_tools=recommended_tools,
        comparison_table=comparison_table,
        review_themes=review_themes,
        evidence_snippets=evidence,
        enterprise_metadata=enterprise_metadata,
        vendor_metadata=vendor_metadata,
        open_source_alternatives=open_source_alternatives,
        required_features=required_features,
        ranking_explanation=ranking_explanation,
        risks=risks,
        follow_up_questions=follow_ups,
        confidence=confidence,
        llm_provider=llm_result.provider,
        llm_model=llm_result.model,
        llm_status=llm_result.status,
        llm_warning=llm_result.warning,
    )


def list_categories() -> list[str]:
    products, _, _ = load_processed_or_demo()
    categories = sorted(
        [item for item in products.get("category", pd.Series(dtype=str)).dropna().unique() if str(item)]
    )
    return ["All", *categories]


def list_product_names() -> list[str]:
    products, _, _ = load_processed_or_demo()
    return sorted(products.get("product_name", pd.Series(dtype=str)).dropna().astype(str).unique())


def list_available_features() -> list[str]:
    products, _, _ = load_processed_or_demo()
    return feature_columns(products)


def display_feature_name(feature: str) -> str:
    return feature_display_name(feature)


def _select_products(
    products: pd.DataFrame,
    query: str,
    category: str | None,
    max_monthly_price: float | None,
    compare_tools_text: str | None,
    top_k: int,
) -> pd.DataFrame:
    if compare_tools_text and split_terms(compare_tools_text):
        matched = match_product_names(products, compare_tools_text)
        if not matched.empty:
            matched = matched.copy()
            matched["retrieval_score"] = 1.0
            matched["retrieval_backend"] = "name_match"
            return matched

    filtered = apply_product_filters(
        products,
        category=category,
        max_monthly_price=max_monthly_price,
        include_unknown_price=True,
    )
    if filtered.empty:
        return filtered
    where = {"category": category} if category and category != "All" else None
    results = search_rows(
        filtered,
        query=query,
        text_column="product_doc",
        top_k=top_k,
        collection_name="products",
        id_prefix="product",
        where=where,
    )
    rows = []
    for result in results:
        row = result.row
        row["retrieval_score"] = result.score
        rows.append(row)
    return pd.DataFrame(rows)


def _retrieve_review_evidence(
    reviews: pd.DataFrame,
    products: pd.DataFrame,
    query: str,
    max_snippets: int,
) -> pd.DataFrame:
    if reviews.empty or products.empty:
        return pd.DataFrame(
            columns=["product_name", "rating", "review_title", "pros", "cons", "snippet", "score"]
        )

    product_names = set(products["normalized_name"].fillna("").map(normalize_name))
    subset = reviews[reviews["normalized_name"].fillna("").map(normalize_name).isin(product_names)].copy()
    if subset.empty:
        return pd.DataFrame(
            columns=["product_name", "rating", "review_title", "pros", "cons", "snippet", "score"]
        )

    where = _review_where_clause(product_names)
    results = search_rows(
        subset,
        query=query,
        text_column="review_doc",
        top_k=max_snippets,
        collection_name="reviews",
        id_prefix="review",
        where=where,
        oversample=20,
    )
    rows: list[dict[str, Any]] = []
    for result in results:
        row = result.row
        rows.append(
            {
                "product_name": _clean_text(row.get("product_name", "")),
                "rating": row.get("rating", ""),
                "review_title": _clean_text(row.get("review_title", "")),
                "pros": _clean_text(row.get("pros", "")),
                "cons": _clean_text(row.get("cons", "")),
                "snippet": _snippet(row),
                "score": round(result.score, 3),
                "retrieval_backend": row.get("retrieval_backend", ""),
            }
        )
    return pd.DataFrame(rows)


def _review_where_clause(product_names: set[str]) -> dict[str, Any] | None:
    names = sorted(name for name in product_names if name)
    if not names:
        return None
    if len(names) == 1:
        return {"normalized_name": names[0]}
    return {"normalized_name": {"$in": names}}


def _snippet(row: dict[str, Any]) -> str:
    parts = []
    pros = _clean_text(row.get("pros"))
    cons = _clean_text(row.get("cons"))
    review = _clean_text(row.get("review_text"))
    if pros:
        parts.append(_snippet_part("Pros", pros))
    if cons:
        parts.append(_snippet_part("Cons", cons))
    if review:
        parts.append(_snippet_part("Review", review))
    return " ".join(parts)


def _snippet_part(label: str, text: str) -> str:
    lowered = text.lower()
    for prefix in ("pros:", "cons:", "review:"):
        if lowered.startswith(prefix):
            return f"{prefix[:-1].title()}: {text[len(prefix):].strip()}"
    return f"{label}: {text}"


def _review_themes(evidence: pd.DataFrame) -> pd.DataFrame:
    if evidence.empty:
        return pd.DataFrame(columns=["Product", "Review coverage", "Pros observed", "Cons observed"])
    rows = []
    for product_name, group in evidence.groupby("product_name"):
        pros = _join_unique(group["pros"].dropna().astype(str).tolist())
        cons = _join_unique(group["cons"].dropna().astype(str).tolist())
        rows.append(
            {
                "Product": product_name,
                "Review coverage": f"{len(group)} retrieved snippet(s)",
                "Pros observed": pros or "No pros retrieved",
                "Cons observed": cons or "No cons retrieved",
            }
        )
    return pd.DataFrame(rows)


def _comparison_table(products: pd.DataFrame, required_features: list[str]) -> pd.DataFrame:
    rows = []
    for _, row in products.iterrows():
        rows.append(
            {
                "Product": row.get("product_name", ""),
                "Category": row.get("category", ""),
                "Pricing": row.get("pricing_summary", "pricing unavailable"),
                "Pricing Source": row.get("pricing_source_type", ""),
                "Pricing Source URLs": row.get("pricing_source_urls", ""),
                "FactGrid Status": row.get("factgrid_status", "missing"),
                "FactGrid Pricing": row.get("factgrid_pricing_summary", "no FactGrid pricing evidence"),
                "FactGrid SLA": row.get("factgrid_sla_summary", "no FactGrid SLA evidence"),
                "FactGrid API": row.get("factgrid_api_summary", "no FactGrid API evidence"),
                "FactGrid Sources": row.get("factgrid_source_urls", ""),
                "Pricing Conflict": bool(row.get("pricing_conflict_flag", False)),
                "Wikidata Entity": row.get("wikidata_label", ""),
                "Vendor Country": row.get("wikidata_country", ""),
                "Feature source": row.get("feature_evidence_source", ""),
                "Feature Evidence Quality": row.get("feature_evidence_quality", ""),
                "Feature fit": f"{row.get('feature_fit_score', 0):.0%}",
                "Matched features": row.get("matched_features") or "No explicit feature requirements mapped",
                "Missing features": row.get("missing_features") or "None from mapped requirements",
                "Review rating": _format_rating(row.get("average_review_rating")),
                "Review count": int(row.get("review_count", 0) or 0),
                "Score": round(float(row.get("final_score", 0)), 3),
                "Retriever": row.get("retrieval_backend", ""),
            }
        )
    return pd.DataFrame(rows)


def _recommended_table(products: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "product_name",
        "category",
        "pricing_summary",
        "pricing_source_type",
        "factgrid_status",
        "factgrid_pricing_summary",
        "wikidata_label",
        "wikidata_country",
        "present_features",
        "feature_evidence_source",
        "feature_evidence_quality",
        "review_count",
        "average_review_rating",
        "final_score",
        "retrieval_backend",
    ]
    available = [column for column in columns if column in products.columns]
    out = products[available].copy()
    rename = {
        "product_name": "Product",
        "category": "Category",
        "pricing_summary": "Pricing Summary",
        "pricing_source_type": "Pricing Source",
        "factgrid_status": "FactGrid Status",
        "factgrid_pricing_summary": "FactGrid Pricing",
        "wikidata_label": "Wikidata Entity",
        "wikidata_country": "Vendor Country",
        "present_features": "Feature Evidence",
        "feature_evidence_source": "Feature Source",
        "feature_evidence_quality": "Feature Evidence Quality",
        "review_count": "Review Count",
        "average_review_rating": "Avg Review Rating",
        "final_score": "Score",
        "retrieval_backend": "Retriever",
    }
    out = out.rename(columns=rename)
    if "Score" in out.columns:
        out["Score"] = out["Score"].astype(float).round(3)
    return out


def _enterprise_metadata(products: pd.DataFrame) -> pd.DataFrame:
    if products.empty or "factgrid_status" not in products.columns:
        return pd.DataFrame(
            columns=[
                "Product",
                "FactGrid Status",
                "Pricing",
                "SLA",
                "API",
                "Source URLs",
                "Accessed",
                "Pricing Conflict",
            ]
        )
    rows = []
    for _, row in products.iterrows():
        status = _clean_text(row.get("factgrid_status", "missing")).lower()
        if not status or status == "missing":
            continue
        rows.append(
            {
                "Product": row.get("product_name", ""),
                "FactGrid Status": row.get("factgrid_status", ""),
                "Pricing": row.get("factgrid_pricing_summary", "no FactGrid pricing evidence"),
                "SLA": row.get("factgrid_sla_summary", "no FactGrid SLA evidence"),
                "API": row.get("factgrid_api_summary", "no FactGrid API evidence"),
                "Source URLs": row.get("factgrid_source_urls", ""),
                "Accessed": row.get("factgrid_accessed", ""),
                "Pricing Conflict": bool(row.get("pricing_conflict_flag", False)),
            }
        )
    return pd.DataFrame(rows)


def _vendor_metadata(products: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Product",
        "Wikidata ID",
        "Label",
        "Entity Types",
        "Official Website",
        "Country",
        "Inception",
        "Parent Organization",
        "Stock Ticker",
        "Source URL",
        "Accessed",
        "Match Method",
        "Match Confidence",
    ]
    if products.empty or "wikidata_id" not in products.columns:
        return pd.DataFrame(columns=columns)
    rows = []
    for _, row in products.iterrows():
        wikidata_id = _clean_text(row.get("wikidata_id", ""))
        if not wikidata_id:
            continue
        rows.append(
            {
                "Product": row.get("product_name", ""),
                "Wikidata ID": wikidata_id,
                "Label": row.get("wikidata_label", ""),
                "Entity Types": row.get("wikidata_entity_types", ""),
                "Official Website": row.get("wikidata_official_website", ""),
                "Country": row.get("wikidata_country", ""),
                "Inception": row.get("wikidata_inception", ""),
                "Parent Organization": row.get("wikidata_parent_org", ""),
                "Stock Ticker": row.get("wikidata_stock_ticker", ""),
                "Source URL": row.get("wikidata_source_url", ""),
                "Accessed": row.get("wikidata_accessed", ""),
                "Match Method": row.get("wikidata_match_method", ""),
                "Match Confidence": row.get("wikidata_match_confidence", ""),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _ranking_explanation(
    products: pd.DataFrame, evidence: pd.DataFrame, required_features: list[str]
) -> list[str]:
    if products.empty:
        return ["No products were available for ranking after filters were applied."]

    top = products.iloc[0]
    explanations = [
        f"Top result `{top.get('product_name', '')}` ranked highest with score {float(top.get('final_score', 0)):.2f}.",
        f"Feature fit contributed {float(top.get('feature_fit_score', 0)):.0%}"
        + (
            f" against mapped requirements: {', '.join(required_features)}."
            if required_features
            else "; no explicit feature requirements were mapped."
        ),
        f"Pricing signal: {top.get('pricing_summary', 'pricing unavailable')}.",
        f"Feature evidence quality: {top.get('feature_evidence_quality', 'unknown')}.",
        f"Review coverage: {int(top.get('review_count', 0) or 0)} linked review(s)"
        + (
            f" and {len(evidence)} retrieved snippet(s)."
            if not evidence.empty
            else "; no review snippets were retrieved for this answer."
        ),
        f"Retriever: {top.get('retrieval_backend', 'unknown')}.",
    ]
    factgrid_status = _clean_text(top.get("factgrid_status", "missing"))
    if factgrid_status and factgrid_status.lower() != "missing":
        explanations.insert(
            -1,
            f"Enterprise metadata: FactGrid status {factgrid_status}; {top.get('factgrid_pricing_summary', 'no FactGrid pricing evidence')}.",
        )
    return explanations


def _risks(products: pd.DataFrame, required_features: list[str], source_notice: str) -> list[str]:
    risks: list[str] = []
    if "fictional demo data" in source_notice.lower():
        risks.append("Demo data is fictional and should not be used for real vendor decisions.")
    if products["pricing_summary"].fillna("").str.contains("pricing unavailable", case=False).any():
        risks.append("At least one retrieved tool has missing pricing data.")
    if products.get("review_count", pd.Series(dtype=int)).fillna(0).eq(0).any():
        risks.append("At least one retrieved tool has no linked review evidence.")
    if required_features and products.get("missing_features", pd.Series(dtype=str)).fillna("").ne("").any():
        risks.append("Some mapped required features are missing for one or more shortlisted tools.")
    if _uses_review_derived_feature_evidence(products, required_features):
        risks.append("Some feature evidence comes from review metadata, not vendor-confirmed feature flags.")
    if products.get("matched_factgrid_features", pd.Series(dtype=str)).fillna("").astype(str).str.strip().ne("").any():
        risks.append("Some API evidence comes from FactGrid enterprise metadata, not the structured feature matrix.")
    if products.get("pricing_conflict_flag", pd.Series(dtype=bool)).fillna(False).astype(bool).any():
        risks.append("At least one product has a possible pricing mismatch between local pricing data and FactGrid metadata.")
    if not risks:
        risks.append("Evidence is limited to the loaded datasets and should be verified with current vendor materials.")
    return risks


def _follow_ups(required_features: list[str], price_ceiling: float | None) -> list[str]:
    questions = [
        "Verify current pricing, contract minimums, and add-on costs with each vendor.",
        "Confirm implementation effort, admin complexity, and integration requirements.",
        "Ask vendors for customer references from companies with a similar size and workflow.",
    ]
    if required_features:
        questions.insert(
            0,
            f"Validate the mapped must-have features in a live demo: {', '.join(required_features)}.",
        )
    if price_ceiling is not None:
        questions.insert(1, f"Confirm whether the real per-seat cost stays under ${price_ceiling:g}.")
    return questions


def _confidence(products: pd.DataFrame, evidence: pd.DataFrame, required_features: list[str]) -> str:
    if products.empty:
        return "low"
    price_coverage = (
        ~products["pricing_summary"].fillna("").str.contains("pricing unavailable", case=False)
    ).mean()
    review_coverage = products.get("review_count", pd.Series([0] * len(products))).fillna(0).gt(0).mean()
    feature_coverage = 1.0
    if required_features:
        feature_coverage = products.get("feature_fit_score", pd.Series([0] * len(products))).mean()
    evidence_coverage = 1.0 if not evidence.empty else 0.0
    score = 0.30 * price_coverage + 0.25 * review_coverage + 0.30 * feature_coverage + 0.15 * evidence_coverage
    review_match_share = _review_derived_match_share(products, required_features)
    if review_match_share >= 1.0:
        score -= 0.30
    elif review_match_share > 0:
        score -= 0.15
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _context_for_llm(
    scored: pd.DataFrame,
    evidence: pd.DataFrame,
    required_features: list[str],
    risks: list[str],
    confidence: str,
    enterprise_metadata: pd.DataFrame | None = None,
    vendor_metadata: pd.DataFrame | None = None,
    open_source_alternatives: pd.DataFrame | None = None,
) -> str:
    context_columns = [
        "product_name",
        "category",
        "pricing_summary",
        "pricing_source_type",
        "pricing_source_urls",
        "pricing_source_accessed",
        "factgrid_status",
        "factgrid_pricing_summary",
        "factgrid_sla_summary",
        "factgrid_api_summary",
        "factgrid_source_urls",
        "factgrid_accessed",
        "pricing_conflict_flag",
        "wikidata_label",
        "wikidata_entity_types",
        "wikidata_country",
        "wikidata_inception",
        "wikidata_parent_org",
        "wikidata_stock_ticker",
        "wikidata_source_url",
        "feature_evidence_source",
        "feature_evidence_quality",
        "matched_features",
        "missing_features",
        "review_count",
        "average_review_rating",
        "final_score",
    ]
    product_context = scored[[column for column in context_columns if column in scored.columns]].to_dict(
        "records"
    )
    review_context = evidence.to_dict("records") if not evidence.empty else []
    enterprise_context = (
        enterprise_metadata.to_dict("records")
        if enterprise_metadata is not None and not enterprise_metadata.empty
        else []
    )
    vendor_context = (
        vendor_metadata.to_dict("records")
        if vendor_metadata is not None and not vendor_metadata.empty
        else []
    )
    alternative_context = (
        open_source_alternatives.to_dict("records")
        if open_source_alternatives is not None and not open_source_alternatives.empty
        else []
    )
    return (
        f"Mapped required features: {required_features}\n"
        f"Confidence: {confidence}\n"
        f"Structured product evidence: {product_context}\n"
        f"FactGrid enterprise metadata: {enterprise_context}\n"
        f"Wikidata vendor facts: {vendor_context}\n"
        f"Review evidence: {review_context}\n"
        f"Open-source alternatives: {alternative_context}\n"
        f"Known risks: {risks}"
    )


def _template_answer(
    query: str,
    scored: pd.DataFrame,
    evidence: pd.DataFrame,
    required_features: list[str],
    ranking_explanation: list[str],
    risks: list[str],
    follow_ups: list[str],
    confidence: str,
    source_notice: str,
    enterprise_metadata: pd.DataFrame | None = None,
    vendor_metadata: pd.DataFrame | None = None,
    open_source_alternatives: pd.DataFrame | None = None,
) -> str:
    top = scored.iloc[0]
    shortlist = ", ".join(scored["product_name"].head(3).astype(str).tolist())
    lines = [
        f"Direct answer: shortlist {shortlist}. The top fit from the loaded evidence is {top['product_name']} for this query.",
        "",
        "Recommended tools:",
    ]
    for _, row in scored.head(5).iterrows():
        matched = row.get("matched_features") or "no explicit feature requirements mapped"
        missing = row.get("missing_features") or "none from mapped requirements"
        lines.append(
            f"- {row['product_name']}: score {float(row['final_score']):.2f}; pricing: {row.get('pricing_summary', 'pricing unavailable')}; pricing source: {row.get('pricing_source_type', 'missing')}; feature source: {row.get('feature_evidence_source', 'unknown')}; feature quality: {row.get('feature_evidence_quality', 'unknown')}; matched: {matched}; missing: {missing}."
        )

    lines.extend(["", "Evidence summary:"])
    if required_features:
        lines.append(f"- Feature requirements mapped to: {', '.join(required_features)}.")
    else:
        lines.append("- No explicit feature requirements were confidently mapped; ranking used product text, pricing, reviews, and category fit.")
    if evidence.empty:
        lines.append("- Review evidence: no linked review snippets were retrieved for this query.")
    else:
        products_with_reviews = ", ".join(sorted(evidence["product_name"].dropna().astype(str).unique()))
        lines.append(f"- Review evidence retrieved for: {products_with_reviews}.")
    backends = sorted(scored.get("retrieval_backend", pd.Series(dtype=str)).dropna().astype(str).unique())
    if backends:
        lines.append(f"- Product retrieval backend: {', '.join(backends)}.")
    pricing_sources = sorted(scored.get("pricing_source_type", pd.Series(dtype=str)).dropna().astype(str).unique())
    if pricing_sources:
        lines.append(f"- Pricing source type: {', '.join(pricing_sources)}.")
    factgrid_products = (
        enterprise_metadata["Product"].dropna().astype(str).tolist()
        if enterprise_metadata is not None and not enterprise_metadata.empty
        else []
    )
    if factgrid_products:
        lines.append(f"- FactGrid enterprise metadata retrieved for: {', '.join(factgrid_products)}.")
    vendor_products = (
        vendor_metadata["Product"].dropna().astype(str).tolist()
        if vendor_metadata is not None and not vendor_metadata.empty
        else []
    )
    if vendor_products:
        lines.append(f"- Wikidata vendor facts retrieved for: {', '.join(vendor_products)}.")
        lines.append("- Wikidata vendor facts are public metadata, not vendor-confirmed procurement evidence.")

    if open_source_alternatives is not None and not open_source_alternatives.empty:
        lines.extend(["", "Open-source alternatives:"])
        for _, row in open_source_alternatives.head(5).iterrows():
            lines.append(
                f"- {row.get('Tool', '')}: {row.get('Description', '')} Source: OpenAlternative; license: {row.get('License', 'Not listed')}."
            )

    lines.extend(["", "Why this ranking:"])
    lines.extend([f"- {item}" for item in ranking_explanation])

    lines.extend(["", "Risks and tradeoffs:"])
    lines.extend([f"- {risk}" for risk in risks])

    lines.extend(["", f"Confidence: {confidence}.", "", "What to verify next:"])
    lines.extend([f"- {question}" for question in follow_ups])

    if "fictional demo data" in source_notice.lower():
        lines.insert(0, f"Data caveat: {source_notice}")
        lines.insert(1, "")
    return "\n".join(lines)


def _empty_result(source_notice: str, required_features: list[str]) -> AnalysisResult:
    return AnalysisResult(
        answer="No matching tools were found with the current filters. Loosen the category, budget, or compare-tool inputs.",
        source_notice=source_notice,
        recommended_tools=pd.DataFrame(),
        comparison_table=pd.DataFrame(),
        review_themes=pd.DataFrame(),
        evidence_snippets=pd.DataFrame(),
        enterprise_metadata=pd.DataFrame(),
        vendor_metadata=pd.DataFrame(),
        open_source_alternatives=pd.DataFrame(),
        required_features=required_features,
        ranking_explanation=["No products matched the active retrieval filters."],
        risks=["No products matched the active retrieval filters."],
        follow_up_questions=["Try a broader category or remove the price ceiling."],
        confidence="low",
        llm_provider="template",
        llm_model="grounded-template",
        llm_status="not_run",
        llm_warning="",
    )


def _uses_review_derived_feature_evidence(products: pd.DataFrame, required_features: list[str]) -> bool:
    if not required_features:
        return False
    review_features = [feature for feature in required_features if is_review_derived_feature(feature)]
    if not review_features:
        return False
    for _, row in products.iterrows():
        if any(to_bool(row.get(feature, 0)) for feature in review_features):
            return True
    return False


def _review_derived_match_share(products: pd.DataFrame, required_features: list[str]) -> float:
    if products.empty or not required_features:
        return 0.0
    matched = 0
    review_matched = 0
    for _, row in products.iterrows():
        for feature in required_features:
            if to_bool(row.get(feature, 0)):
                matched += 1
                if is_review_derived_feature(feature):
                    review_matched += 1
    if matched == 0:
        return 0.0
    return review_matched / matched


def _join_unique(values: list[Any], limit: int = 4) -> str:
    seen: list[str] = []
    for value in values:
        text = _clean_text(value)
        if text and text not in seen:
            seen.append(text)
    return "; ".join(seen[:limit])


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null"}:
        return ""
    return text


def _format_rating(value: Any) -> str:
    rating = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(rating):
        return "No rating"
    return f"{float(rating):.1f}"
