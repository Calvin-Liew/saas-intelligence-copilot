from __future__ import annotations

import re
from typing import Iterable

import pandas as pd

from .normalizer import normalize_key, normalize_name, split_terms, to_bool


REVIEW_DERIVED_FEATURE_COLUMNS = {
    "ticket_creation_and_assignment",
    "automated_ticket_routing",
    "status_tracking_and_updates",
    "priority_and_sla_management",
    "customer_and_agent_portals",
    "knowledge_base_integration",
    "email_notifications_and_alerts",
    "reporting_and_analytics",
    "customizable_workflows",
    "multi_channel_support_email_chat_phone",
}

FEATURE_SYNONYMS = {
    "automation": ["automation", "automated", "workflow automation", "routing"],
    "automation_workflows": ["automation workflows", "workflow automation"],
    "analytics": ["analytics", "dashboard", "dashboards", "insights", "metrics"],
    "api": ["api", "developer", "developers"],
    "api_access": ["api", "api access", "developer access"],
    "api_integrations": ["integrations", "api integrations", "connectors"],
    "integrations": ["integration", "integrations", "connectors", "apps"],
    "sso": ["sso", "single sign on", "single-sign-on", "identity"],
    "sso_integration": ["sso", "single sign on", "single-sign-on", "identity"],
    "2fa_mfa": ["2fa", "mfa", "multi factor", "two factor"],
    "ai_features": ["ai", "artificial intelligence", "copilot", "assistant"],
    "reporting": ["reporting", "reports", "report"],
    "reporting_analytics": ["analytics reporting", "reporting analytics"],
    "analytics_reporting": ["analytics reporting", "reporting analytics"],
    "customizable_reports": ["custom reports", "custom reporting"],
    "collaboration": ["collaboration", "shared workspace", "team collaboration"],
    "workflow_builder": ["workflow builder", "workflow", "approval workflow"],
    "knowledge_base": ["knowledge base", "help center", "docs", "documentation"],
    "knowledge_base_integration": ["knowledge base", "help center", "self service", "self-service"],
    "ticket_creation_and_assignment": ["ticketing", "ticket creation", "ticket assignment", "issue tracking"],
    "automated_ticket_routing": ["automation", "automated", "routing", "automated ticket routing"],
    "status_tracking_and_updates": ["status tracking", "ticket tracking", "updates", "tracking"],
    "priority_and_sla_management": ["sla", "priority", "priorities", "escalation", "service level"],
    "customer_and_agent_portals": ["portal", "customer portal", "agent portal", "self service"],
    "email_notifications_and_alerts": ["email notifications", "alerts", "notifications"],
    "reporting_and_analytics": ["analytics", "reporting", "reports", "dashboard", "dashboards"],
    "customizable_workflows": ["workflow", "workflows", "custom workflows", "workflow builder"],
    "multi_channel_support_email_chat_phone": [
        "multi channel",
        "multichannel",
        "omnichannel",
        "email chat phone",
        "chat",
        "phone",
    ],
}

PARTIAL_EXPLICIT_TERMS = {
    "2fa",
    "mfa",
}

METADATA_COLUMNS = {
    "product_id",
    "product_name",
    "vendor_name",
    "category",
    "description",
    "website",
    "rating",
    "market_segment",
    "tags",
    "normalized_name",
    "pricing_summary",
    "min_monthly_price",
    "has_free_plan",
    "has_enterprise_plan",
    "review_count",
    "average_review_rating",
    "present_features",
    "feature_evidence_source",
    "feature_evidence_quality",
    "pricing_source_type",
    "pricing_source_urls",
    "pricing_source_accessed",
    "factgrid_slug",
    "factgrid_status",
    "factgrid_pricing_summary",
    "factgrid_starting_price_usd",
    "factgrid_sla_summary",
    "factgrid_api_summary",
    "factgrid_source_urls",
    "factgrid_accessed",
    "pricing_conflict_flag",
    "wikidata_id",
    "wikidata_label",
    "wikidata_entity_types",
    "wikidata_official_website",
    "wikidata_country",
    "wikidata_inception",
    "wikidata_parent_org",
    "wikidata_stock_ticker",
    "wikidata_source_url",
    "wikidata_accessed",
    "wikidata_match_method",
    "wikidata_match_confidence",
    "product_doc",
}

FACTGRID_API_FEATURES = {"api", "api_access"}


def feature_columns(products: pd.DataFrame) -> list[str]:
    columns: list[str] = []
    for column in products.columns:
        if column in METADATA_COLUMNS:
            continue
        values = set(pd.Series(products[column]).dropna().astype(str).str.lower().unique())
        if values.issubset({"0", "1", "0.0", "1.0", "true", "false"}):
            columns.append(column)
    return columns


def review_derived_feature_columns(columns: Iterable[str]) -> list[str]:
    return [column for column in columns if is_review_derived_feature(column)]


def structured_feature_columns(columns: Iterable[str]) -> list[str]:
    return [column for column in columns if not is_review_derived_feature(column)]


def is_review_derived_feature(column: str) -> bool:
    return normalize_key(column) in REVIEW_DERIVED_FEATURE_COLUMNS


def feature_display_name(column: str) -> str:
    return f"{column} (review-derived)" if is_review_derived_feature(column) else column


def extract_price_ceiling(query: str) -> float | None:
    text = str(query or "").lower()
    patterns = [
        r"(?:under|below|less than|up to|max(?:imum)?)\s*\$?\s*(\d+(?:\.\d+)?)",
        r"\$\s*(\d+(?:\.\d+)?)\s*(?:or less|and below|max)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return None


def map_required_features(
    query: str,
    explicit_features: str | Iterable[str] | None,
    available_feature_columns: Iterable[str],
    category: str | None = None,
    candidate_products: pd.DataFrame | None = None,
) -> list[str]:
    available = [
        column
        for column in available_feature_columns
        if _allow_feature(column, query=query, category=category, candidate_products=candidate_products)
    ]
    requested_text = " ".join(split_terms(explicit_features)) if explicit_features else ""
    haystack = f"{query or ''} {requested_text}".lower()
    explicit_terms = [_normalize_feature_term(term) for term in split_terms(explicit_features)]

    matched: list[str] = []
    for column in available:
        key = normalize_key(column)
        synonyms = FEATURE_SYNONYMS.get(key, [])
        column_words = key.replace("_", " ")
        key_parts = set(key.split("_"))
        if key in explicit_terms or _contains_phrase(haystack, column_words):
            matched.append(column)
            continue
        if any(_contains_phrase(haystack, term) for term in synonyms):
            matched.append(column)
            continue
        if any(
            term
            and term in PARTIAL_EXPLICIT_TERMS
            and (term in key_parts or term == key)
            for term in explicit_terms
        ):
            matched.append(column)

    return list(dict.fromkeys(matched))


def _allow_feature(
    column: str,
    query: str,
    category: str | None,
    candidate_products: pd.DataFrame | None,
) -> bool:
    if not is_review_derived_feature(column):
        return True
    return _is_support_context(query=query, category=category, candidate_products=candidate_products)


def _is_support_context(
    query: str,
    category: str | None,
    candidate_products: pd.DataFrame | None,
) -> bool:
    if category and normalize_name(category) == "customer support":
        return True
    if candidate_products is not None and not candidate_products.empty:
        categories = candidate_products.get("category", pd.Series(dtype=str)).fillna("").map(normalize_name)
        if categories.eq("customer support").any():
            return True
    query_text = normalize_name(query)
    support_terms = {"support", "ticket", "ticketing", "help desk", "service desk", "customer support"}
    return any(term in query_text for term in support_terms)


def _normalize_feature_term(term: str) -> str:
    key = normalize_key(term)
    suffix = "_review_derived"
    if key.endswith(suffix):
        return key[: -len(suffix)]
    return key


def _contains_phrase(text: str, phrase: str) -> bool:
    phrase = normalize_name(phrase)
    if not phrase:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def score_products(
    products: pd.DataFrame,
    required_features: list[str],
    query: str = "",
    category: str | None = None,
    max_monthly_price: float | None = None,
) -> pd.DataFrame:
    if products.empty:
        return products.copy()

    scored = products.copy()
    scored["matched_features"] = scored.apply(
        lambda row: ", ".join(
            [
                _feature_match_label(row, feature)
                for feature in required_features
                if _feature_matches(row, feature)
            ]
        ),
        axis=1,
    )
    scored["missing_features"] = scored.apply(
        lambda row: ", ".join(
            [feature for feature in required_features if not _feature_matches(row, feature)]
        ),
        axis=1,
    )
    scored["feature_fit_score"] = scored.apply(
        lambda row: _feature_score(row, required_features), axis=1
    )
    scored["matched_review_derived_features"] = scored.apply(
        lambda row: ", ".join(
            [
                feature
                for feature in required_features
                if is_review_derived_feature(feature) and to_bool(row.get(feature, 0))
            ]
        ),
        axis=1,
    )
    scored["matched_structured_features"] = scored.apply(
        lambda row: ", ".join(
            [
                feature
                for feature in required_features
                if not is_review_derived_feature(feature) and to_bool(row.get(feature, 0))
            ]
        ),
        axis=1,
    )
    scored["matched_factgrid_features"] = scored.apply(
        lambda row: ", ".join(
            [
                _feature_match_label(row, feature)
                for feature in required_features
                if _factgrid_feature_matches(row, feature)
            ]
        ),
        axis=1,
    )
    factgrid_match_mask = scored["matched_factgrid_features"].fillna("").astype(str).str.strip().ne("")
    if factgrid_match_mask.any():
        scored.loc[factgrid_match_mask, "feature_evidence_source"] = scored.loc[
            factgrid_match_mask, "feature_evidence_source"
        ].fillna("").astype(str).apply(_append_factgrid_source)
        scored.loc[factgrid_match_mask, "feature_evidence_quality"] = scored.loc[
            factgrid_match_mask, "feature_evidence_quality"
        ].fillna("").astype(str).apply(_mixed_feature_quality)
    scored["pricing_score"] = scored.apply(
        lambda row: _pricing_score(row, max_monthly_price), axis=1
    )
    scored["review_score"] = scored.apply(_review_score, axis=1)
    scored["category_fit_score"] = scored.apply(
        lambda row: _category_score(row, query, category), axis=1
    )
    scored["final_score"] = (
        0.45 * scored["feature_fit_score"]
        + 0.25 * scored["pricing_score"]
        + 0.20 * scored["review_score"]
        + 0.10 * scored["category_fit_score"]
    )
    return scored.sort_values("final_score", ascending=False).reset_index(drop=True)


def _feature_score(row: pd.Series, required_features: list[str]) -> float:
    if not required_features:
        return 1.0
    matched = sum(1 for feature in required_features if _feature_matches(row, feature))
    return matched / len(required_features)


def _feature_matches(row: pd.Series, feature: str) -> bool:
    return to_bool(row.get(feature, 0)) or _factgrid_feature_matches(row, feature)


def _factgrid_feature_matches(row: pd.Series, feature: str) -> bool:
    key = normalize_key(feature)
    if key in FACTGRID_API_FEATURES:
        summary = str(row.get("factgrid_api_summary", "") or "").strip().lower()
        return bool(summary and summary != "no factgrid api evidence")
    return False


def _feature_match_label(row: pd.Series, feature: str) -> str:
    if _factgrid_feature_matches(row, feature) and not to_bool(row.get(feature, 0)):
        return f"{feature} (FactGrid API metadata)"
    return feature


def _append_factgrid_source(source: str) -> str:
    source = source.strip()
    factgrid_source = "FactGrid enterprise metadata"
    if not source:
        return factgrid_source
    if factgrid_source.lower() in source.lower():
        return source
    return f"{source}; {factgrid_source}"


def _mixed_feature_quality(quality: str) -> str:
    quality = quality.strip() or "missing"
    if quality == "missing":
        return "factgrid"
    if quality == "factgrid":
        return quality
    if quality == "mixed":
        return quality
    return "mixed"


def _pricing_score(row: pd.Series, max_monthly_price: float | None) -> float:
    price = pd.to_numeric(pd.Series([row.get("min_monthly_price")]), errors="coerce").iloc[0]
    has_free = bool(row.get("has_free_plan", False))
    enterprise = bool(row.get("has_enterprise_plan", False))
    if pd.isna(price):
        return 0.45 if enterprise else 0.35
    if max_monthly_price:
        score = 1.0 if price <= max_monthly_price else max(0.0, 1 - ((price - max_monthly_price) / max_monthly_price))
    else:
        score = 1 / (1 + (float(price) / 100))
    if has_free:
        score += 0.1
    return min(score, 1.0)


def _review_score(row: pd.Series) -> float:
    rating = pd.to_numeric(pd.Series([row.get("average_review_rating")]), errors="coerce").iloc[0]
    if pd.isna(rating):
        return 0.5
    return max(0.0, min(float(rating) / 5, 1.0))


def _category_score(row: pd.Series, query: str, category: str | None) -> float:
    row_category = normalize_name(row.get("category", ""))
    if category and category != "All":
        return 1.0 if normalize_name(category) == row_category else 0.0
    query_text = normalize_name(query)
    if row_category and row_category in query_text:
        return 1.0
    category_terms = set(row_category.split())
    query_terms = set(query_text.split())
    if category_terms & query_terms:
        return 0.8
    return 0.5
