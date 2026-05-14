from __future__ import annotations

import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from .config import PATHS, RUNTIME
from .demo_data import DEMO_NOTICE, demo_features, demo_pricing, demo_products, demo_reviews
from .enrichment import (
    apply_factgrid_enrichment,
    apply_wikidata_enrichment,
    ensure_factgrid_columns,
    ensure_wikidata_columns,
)
from .normalizer import compact_text, normalize_key, normalize_name, to_bool, to_number


PRODUCT_COLUMNS = [
    "product_name",
    "ticket_system",
    "product",
    "tool_name",
    "software_name",
    "app_name",
    "name",
]

REVIEW_CORE_COLUMNS = {
    "product_name",
    "review_title",
    "review_text",
    "pros",
    "cons",
    "rating",
    "review_date",
    "normalized_name",
    "review_doc",
    "source_type",
    "ease_of_use",
    "customer_service",
    "features",
    "value_for_money",
    "likelihood_to_recommend",
}

PROCESSED_ARTIFACT_FILES = [
    "product_master.csv",
    "review_chunks.csv",
    "unmatched_records.csv",
    "evaluation_results.csv",
    "factgrid_enrichment.csv",
    "wikidata_vendor_facts.csv",
    "open_source_alternatives.csv",
    "enrichment_qa.csv",
]
DOWNLOAD_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}

_PROCESSED_CACHE: dict[
    tuple[object, ...], tuple[pd.DataFrame, pd.DataFrame, str]
] = {}


def pick_column(
    df: pd.DataFrame, candidates: Iterable[str], contains: Iterable[str] = ()
) -> str | None:
    lower_to_original = {str(col).lower().strip(): col for col in df.columns}
    for candidate in candidates:
        if candidate.lower() in lower_to_original:
            return lower_to_original[candidate.lower()]
    contains = [item.lower() for item in contains]
    for lowered, original in lower_to_original.items():
        if any(term in lowered for term in contains):
            return original
    return None


def _series_or_default(df: pd.DataFrame, column: str | None, default: object = "") -> pd.Series:
    if column and column in df.columns:
        return df[column]
    return pd.Series([default] * len(df), index=df.index)


def _coalesced_series(
    df: pd.DataFrame,
    candidates: Iterable[str],
    default: object = "",
    contains: Iterable[str] = (),
) -> pd.Series:
    columns: list[str] = []
    lower_to_original = {str(col).lower().strip(): col for col in df.columns}
    for candidate in candidates:
        column = lower_to_original.get(candidate.lower())
        if column and column not in columns:
            columns.append(column)
    contains = [item.lower() for item in contains]
    for lowered, original in lower_to_original.items():
        if original in columns:
            continue
        if any(term in lowered for term in contains):
            columns.append(original)

    if not columns:
        return pd.Series([default] * len(df), index=df.index)

    out = pd.Series([pd.NA] * len(df), index=df.index, dtype="object")
    for column in columns:
        values = df[column]
        present = values.notna() & values.astype(str).str.strip().ne("")
        out = out.where(out.notna(), values.where(present))
    if default is None:
        return out.where(out.notna(), None)
    return out.fillna(default)


def _unique_columns(columns: Iterable[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique: list[str] = []
    for column in columns:
        base = normalize_key(column) or "feature"
        count = seen.get(base, 0)
        seen[base] = count + 1
        unique.append(base if count == 0 else f"{base}_{count + 1}")
    return unique


def _is_binary_feature_column(series: pd.Series) -> bool:
    values = series.dropna().astype(str).str.strip().str.lower()
    if values.empty:
        return False
    return set(values.unique()).issubset({"0", "1", "0.0", "1.0", "true", "false"})


def _pricing_notes(df: pd.DataFrame, notes_col: str | None, highlight_cols: list[str]) -> pd.Series:
    highlight_notes = (
        df[highlight_cols].fillna("").astype(str).apply(
            lambda row: "; ".join([value.strip() for value in row if value.strip() and value != "nan"]),
            axis=1,
        )
        if highlight_cols
        else pd.Series([""] * len(df), index=df.index)
    )
    if notes_col and notes_col in df.columns:
        notes = df[notes_col].fillna("").astype(str).str.strip()
        return notes.where(notes.ne(""), highlight_notes)
    return highlight_notes


def read_table(path: str | Path, table: str | None = None, role: str = "products") -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".sqlite", ".sqlite3", ".db"}:
        return read_sqlite_table(path, table=table, role=role)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    raise ValueError(f"Unsupported data file type: {path}")


def read_sqlite_table(path: Path, table: str | None = None, role: str = "products") -> pd.DataFrame:
    with sqlite3.connect(path) as conn:
        tables = pd.read_sql_query(
            "select name from sqlite_master where type='table' order by name", conn
        )["name"].tolist()
        if not tables:
            raise ValueError(f"No tables found in SQLite database: {path}")
        if not table and role == "products" and {"products", "categories"}.issubset(set(tables)):
            return pd.read_sql_query(
                """
                select
                    p.id as product_id,
                    p.name as product_name,
                    c.name as category,
                    p.description,
                    p.short_description,
                    p.website_url as website,
                    p.overall_rating as rating,
                    p.review_count,
                    p.has_free_tier,
                    p.has_free_trial,
                    p.last_updated,
                    p.comparedge_url
                from products p
                left join categories c on c.id = p.category_id
                """,
                conn,
            )
        table_name = table or choose_sqlite_table(conn, tables, role)
        return pd.read_sql_query(f'select * from "{table_name}"', conn)


def choose_sqlite_table(conn: sqlite3.Connection, tables: list[str], role: str) -> str:
    terms_by_role = {
        "products": ["product", "tool", "software", "category", "vendor", "description"],
        "pricing": ["price", "pricing", "plan", "monthly", "enterprise", "free"],
        "features": ["feature", "automation", "analytics", "integration", "api", "sso"],
        "reviews": ["review", "pros", "cons", "rating", "capterra"],
    }
    terms = terms_by_role.get(role, terms_by_role["products"])
    best_table = tables[0]
    best_score = -1
    for table in tables:
        columns = pd.read_sql_query(f'pragma table_info("{table}")', conn)["name"].tolist()
        haystack = " ".join([table, *columns]).lower()
        score = sum(term in haystack for term in terms)
        score += min(len(columns), 50) / 100
        if score > best_score:
            best_score = score
            best_table = table
    return best_table


def discover_raw_file(raw_dir: Path, role: str) -> Path | None:
    role_terms = {
        "products": ["sqlite", "saas-db", "saas_db", "market", "product", "tool"],
        "pricing": ["pricing", "price", "plans"],
        "features": ["feature", "matrix"],
        "reviews": ["review", "capterra", "ticket"],
    }
    supported = {".csv", ".xlsx", ".xls", ".parquet", ".json", ".jsonl", ".sqlite", ".sqlite3", ".db"}
    files = [path for path in raw_dir.rglob("*") if path.is_file() and path.suffix.lower() in supported]
    terms = role_terms[role]
    scored: list[tuple[int, Path]] = []
    for path in files:
        text = str(path).lower()
        score = sum(term in text for term in terms)
        if role == "products" and path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
            score += 2
        scored.append((score, path))
    scored = [item for item in scored if item[0] > 0]
    if not scored:
        return None
    return sorted(scored, key=lambda item: (-item[0], len(str(item[1]))))[0][1]


def canonicalize_products(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _empty_products()

    product_col = pick_column(df, PRODUCT_COLUMNS)
    vendor_col = pick_column(df, ["vendor_name", "vendor", "company", "publisher"], ["vendor"])
    category_col = pick_column(df, ["category", "primary_category", "software_category"], ["category"])
    description_col = pick_column(
        df, ["description", "overview", "summary", "about", "short_description"], ["description"]
    )
    website_col = pick_column(df, ["website", "url", "homepage", "product_url"], ["website", "url"])
    rating_col = pick_column(df, ["rating", "average_rating", "review_rating"], ["rating"])
    segment_col = pick_column(df, ["market_segment", "segment", "company_size"], ["segment"])
    tags_col = pick_column(df, ["tags", "keywords", "labels"], ["tag"])
    product_id_col = pick_column(df, ["product_id", "id", "tool_id", "software_id"])

    product_names = _series_or_default(df, product_col, "")
    out = pd.DataFrame(
        {
            "product_id": _series_or_default(df, product_id_col, "").astype(str),
            "product_name": product_names.astype(str).str.strip(),
            "vendor_name": _series_or_default(df, vendor_col, "").astype(str).str.strip(),
            "category": _series_or_default(df, category_col, "").astype(str).str.strip(),
            "description": _series_or_default(df, description_col, "").astype(str).str.strip(),
            "website": _series_or_default(df, website_col, "").astype(str).str.strip(),
            "rating": _series_or_default(df, rating_col, None).map(to_number),
            "market_segment": _series_or_default(df, segment_col, "").astype(str).str.strip(),
            "tags": _series_or_default(df, tags_col, "").astype(str).str.strip(),
        }
    )
    out = out[out["product_name"].astype(str).str.strip() != ""].copy()
    out["normalized_name"] = out["product_name"].map(normalize_name)
    missing_ids = out["product_id"].astype(str).str.strip() == ""
    out.loc[missing_ids, "product_id"] = out.loc[missing_ids, "product_name"].map(normalize_key)
    return out.drop_duplicates("normalized_name").reset_index(drop=True)


def canonicalize_pricing(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _empty_pricing()

    product_col = pick_column(df, PRODUCT_COLUMNS)
    plan_col = pick_column(df, ["plan_name", "plan", "tier", "pricing_tier"], ["plan", "tier"])
    source_type_col = pick_column(df, ["pricing_source_type", "source_type"])
    source_url_col = pick_column(df, ["source_url", "pricing_source_url", "source_uri"])
    source_accessed_col = pick_column(df, ["source_accessed", "pricing_source_accessed", "accessed"])
    price_values = _coalesced_series(
        df,
        ["monthly_price", "price_monthly", "plan_price_usd", "price", "monthly", "amount"],
        default=None,
    )
    unit_values = _coalesced_series(
        df,
        ["billing_unit", "billing_period", "unit", "per"],
        default="",
    )
    free_values = _coalesced_series(df, ["free_plan", "has_free_plan", "free"], default=False)
    enterprise_values = _coalesced_series(
        df, ["enterprise_plan", "has_enterprise_plan", "enterprise"], default=False
    )
    source_url_values = _series_or_default(df, source_url_col, "").fillna("").astype(str).str.strip()
    source_type_values = (
        _series_or_default(df, source_type_col, "").fillna("").astype(str).str.strip().str.lower()
    )
    inferred_source_type = source_url_values.map(lambda value: "supplemental" if value else "kaggle")
    source_type_values = source_type_values.where(source_type_values.ne(""), inferred_source_type)
    notes_col = pick_column(df, ["pricing_notes", "notes", "description", "details"], ["note", "detail"])
    highlight_cols = [col for col in df.columns if str(col).lower().startswith("highlight_")]

    out = pd.DataFrame(
        {
            "product_name": _series_or_default(df, product_col, "").astype(str).str.strip(),
            "plan_name": _series_or_default(df, plan_col, "Plan").astype(str).str.strip(),
            "monthly_price": price_values.map(to_number),
            "billing_unit": unit_values.astype(str).str.strip(),
            "free_plan": free_values.map(to_bool),
            "enterprise_plan": enterprise_values.map(to_bool),
            "pricing_notes": _pricing_notes(df, notes_col, highlight_cols),
            "pricing_source_type": source_type_values,
            "source_url": source_url_values,
            "source_accessed": _series_or_default(df, source_accessed_col, "")
            .fillna("")
            .astype(str)
            .str.strip(),
        }
    )
    plan_text = out["plan_name"].fillna("").astype(str).str.lower()
    out["enterprise_plan"] = out["enterprise_plan"] | plan_text.str.contains(
        "enterprise|custom|contact"
    )
    out = out[out["product_name"].astype(str).str.strip() != ""].copy()
    out["normalized_name"] = out["product_name"].map(normalize_name)
    return out.reset_index(drop=True)


def canonicalize_features(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _empty_features()

    product_col = pick_column(df, PRODUCT_COLUMNS)
    if not product_col:
        return _empty_features()

    excluded = {product_col}
    for candidate in [
        "product_id",
        "id",
        "product_slug",
        "product_url",
        "vendor",
        "vendor_name",
        "category",
        "description",
        "url",
        "website",
        "rating",
        "overall_rating",
        "users_estimate",
        "has_free_plan",
        "lowest_paid_price",
    ]:
        column = pick_column(df, [candidate])
        if column:
            excluded.add(column)

    feature_cols = [
        col for col in df.columns if col not in excluded and _is_binary_feature_column(df[col])
    ]
    renamed_features = _unique_columns(feature_cols)
    feature_data = {
        renamed: df[original].map(to_bool).astype(int)
        for original, renamed in zip(feature_cols, renamed_features)
    }
    out = pd.concat(
        [pd.DataFrame({"product_name": df[product_col].astype(str).str.strip()}), pd.DataFrame(feature_data)],
        axis=1,
    )
    out = out[out["product_name"].astype(str).str.strip() != ""].copy()
    out["normalized_name"] = out["product_name"].map(normalize_name)
    return out.drop_duplicates("normalized_name").reset_index(drop=True)


def canonicalize_reviews(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return _empty_reviews()

    product_col = pick_column(
        df,
        ["product_name", "ticket_system", "product", "tool_name", "software_name", "app_name", "name"],
    )
    title_col = pick_column(df, ["review_title", "title", "subject"], ["title"])
    review_col = pick_column(
        df,
        ["review_text", "overall_text", "review", "text", "body", "comments"],
        ["review", "comment", "overall_text"],
    )
    pros_col = pick_column(df, ["pros", "pros_text", "likes", "advantages"], ["pros", "like"])
    cons_col = pick_column(df, ["cons", "cons_text", "dislikes", "problems"], ["cons", "dislike"])
    rating_col = pick_column(
        df, ["rating", "overall_rating", "score", "stars"], ["overall_rating", "rating", "score"]
    )
    date_col = pick_column(df, ["review_date", "date", "created_at"], ["date"])

    out = pd.DataFrame(
        {
            "product_name": _series_or_default(df, product_col, "").astype(str).str.strip(),
            "review_title": _series_or_default(df, title_col, "").astype(str).str.strip(),
            "review_text": _series_or_default(df, review_col, "").astype(str).str.strip(),
            "pros": _series_or_default(df, pros_col, "").astype(str).str.strip(),
            "cons": _series_or_default(df, cons_col, "").astype(str).str.strip(),
            "rating": _series_or_default(df, rating_col, None).map(to_number),
            "review_date": _series_or_default(df, date_col, "").astype(str).str.strip(),
        }
    )
    out = out[out["product_name"].astype(str).str.strip() != ""].copy()
    out["normalized_name"] = out["product_name"].map(normalize_name)
    review_signal_columns = _review_signal_columns(
        df,
        excluded={product_col, title_col, review_col, pros_col, cons_col, rating_col, date_col},
    )
    for original, renamed in zip(review_signal_columns, _unique_columns(review_signal_columns)):
        out[renamed] = df.loc[out.index, original].map(_review_signal_value).astype(int)
    return out.reset_index(drop=True)


def build_product_master(
    products: pd.DataFrame,
    pricing: pd.DataFrame,
    features: pd.DataFrame,
    reviews: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    products = canonicalize_products(products)
    pricing = canonicalize_pricing(pricing)
    features = canonicalize_features(features)
    reviews = canonicalize_reviews(reviews)

    if products.empty:
        products = canonicalize_products(demo_products())
    products = _append_review_only_products(products, reviews)

    feature_columns = [
        col for col in features.columns if col not in {"product_name", "normalized_name"}
    ]
    master = products.copy()
    if not features.empty:
        feature_frame = features[["normalized_name", *feature_columns]]
        master = master.merge(feature_frame, how="left", on="normalized_name")
    for column in feature_columns:
        master[column] = master[column].fillna(0).astype(int)
    master = master.copy()

    review_features, review_feature_columns = _review_feature_summary_frame(reviews)
    if not review_features.empty:
        master = master.merge(review_features, how="left", on="normalized_name")
    for column in review_feature_columns:
        master[column] = master[column].fillna(0).astype(int)
    all_feature_columns = [*feature_columns, *review_feature_columns]

    pricing_summary = _pricing_summary_frame(pricing)
    review_summary = _review_summary_frame(reviews)
    master = master.merge(pricing_summary, how="left", on="normalized_name")
    master = master.merge(review_summary, how="left", on="normalized_name")

    master["pricing_summary"] = master["pricing_summary"].fillna("pricing unavailable")
    master["pricing_source_type"] = master["pricing_source_type"].fillna("missing")
    master["pricing_source_urls"] = master["pricing_source_urls"].fillna("")
    master["pricing_source_accessed"] = master["pricing_source_accessed"].fillna("")
    master["min_monthly_price"] = master["min_monthly_price"].astype("Float64")
    master["has_free_plan"] = master["has_free_plan"].fillna(False).astype(bool)
    master["has_enterprise_plan"] = master["has_enterprise_plan"].fillna(False).astype(bool)
    master["review_count"] = master["review_count"].fillna(0).astype(int)
    master["average_review_rating"] = master["average_review_rating"].astype("Float64")
    master["feature_evidence_source"] = master.apply(
        lambda row: _feature_evidence_source(row, feature_columns, review_feature_columns),
        axis=1,
    )
    master["feature_evidence_quality"] = master.apply(
        lambda row: _feature_evidence_quality(row, feature_columns, review_feature_columns),
        axis=1,
    )
    master["present_features"] = master.apply(
        lambda row: _present_features(row, feature_columns, review_feature_columns),
        axis=1,
    )
    master = apply_factgrid_enrichment(master)
    master = apply_wikidata_enrichment(master)
    master["product_doc"] = master.apply(_product_doc, axis=1)

    review_chunks = build_review_chunks(reviews)
    unmatched = build_unmatched_records(products, pricing, features, reviews)
    return master.reset_index(drop=True), review_chunks, unmatched


def build_review_chunks(reviews: pd.DataFrame) -> pd.DataFrame:
    reviews = canonicalize_reviews(reviews)
    if reviews.empty:
        return _empty_review_chunks()
    out = reviews.copy()
    out["review_doc"] = out.apply(
        lambda row: compact_text(
            [
                f"Product: {row['product_name']}",
                f"Rating: {row['rating']}" if pd.notna(row["rating"]) else "",
                f"Title: {row['review_title']}",
                f"Pros: {row['pros']}",
                f"Cons: {row['cons']}",
                f"Review: {row['review_text']}",
            ]
        ),
        axis=1,
    )
    out["source_type"] = "review"
    return out.reset_index(drop=True)


def build_unmatched_records(
    products: pd.DataFrame, pricing: pd.DataFrame, features: pd.DataFrame, reviews: pd.DataFrame
) -> pd.DataFrame:
    product_names = set(products.get("normalized_name", pd.Series(dtype=str)).dropna())
    frames = []
    for source, df in [("pricing", pricing), ("features", features), ("reviews", reviews)]:
        if df.empty or "normalized_name" not in df.columns:
            continue
        unmatched = df[~df["normalized_name"].isin(product_names)].copy()
        if unmatched.empty:
            continue
        unmatched["source_table"] = source
        frames.append(unmatched[["source_table", "product_name", "normalized_name"]])
    if not frames:
        return pd.DataFrame(columns=["source_table", "product_name", "normalized_name"])
    return pd.concat(frames, ignore_index=True).drop_duplicates()


def _append_review_only_products(products: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    if reviews.empty or "normalized_name" not in reviews.columns:
        return products

    product_names = set(products["normalized_name"].dropna())
    review_only_names = sorted(set(reviews["normalized_name"].dropna()) - product_names)
    if not review_only_names:
        return products

    rows = []
    for normalized_name in review_only_names:
        group = reviews[reviews["normalized_name"] == normalized_name]
        display_name = str(group["product_name"].dropna().iloc[0])
        rows.append(
            {
                "product_id": f"review_only_{normalize_key(display_name)}",
                "product_name": display_name,
                "vendor_name": "",
                "category": "Customer Support",
                "description": (
                    "Review-only ticketing/support product from the Capterra reviews dataset. "
                    "Structured product, pricing, and feature metadata were not matched in the "
                    "loaded product universe."
                ),
                "website": "",
                "rating": group["rating"].mean(),
                "market_segment": "",
                "tags": "ticketing, support, reviews",
                "normalized_name": normalized_name,
            }
        )
    return pd.concat([products, pd.DataFrame(rows)], ignore_index=True)


def _review_signal_columns(df: pd.DataFrame, excluded: set[str | None]) -> list[str]:
    excluded = {column for column in excluded if column}
    excluded_lower = {str(column).lower() for column in excluded}
    signal_columns: list[str] = []
    for column in df.columns:
        lowered = str(column).lower()
        if lowered in excluded_lower or normalize_key(column) in REVIEW_CORE_COLUMNS:
            continue
        values = df[column].dropna().astype(str).str.strip().str.lower()
        if values.empty:
            continue
        if set(values.unique()).issubset({"-1", "0", "1", "-1.0", "0.0", "1.0"}):
            signal_columns.append(column)
    return signal_columns


def _review_signal_value(value: object) -> int:
    number = to_number(value)
    if number is None:
        return 0
    if number > 0:
        return 1
    if number < 0:
        return -1
    return 0


def _review_feature_summary_frame(reviews: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if reviews.empty or "normalized_name" not in reviews.columns:
        return pd.DataFrame(columns=["normalized_name"]), []

    review_feature_columns = [
        column
        for column in reviews.columns
        if column not in REVIEW_CORE_COLUMNS
        and pd.Series(reviews[column]).dropna().astype(str).str.lower().isin(["-1", "0", "1"]).all()
    ]
    if not review_feature_columns:
        return pd.DataFrame(columns=["normalized_name"]), []

    rows = []
    for normalized_name, group in reviews.groupby("normalized_name"):
        row: dict[str, object] = {"normalized_name": normalized_name}
        review_count = max(len(group), 1)
        minimum_positive_mentions = max(3, int(review_count * 0.05))
        for column in review_feature_columns:
            values = pd.to_numeric(group[column], errors="coerce").fillna(0)
            positive = int(values.eq(1).sum())
            negative = int(values.eq(-1).sum())
            row[column] = int(positive >= minimum_positive_mentions and positive >= negative)
        rows.append(row)
    return pd.DataFrame(rows), review_feature_columns


def _feature_evidence_source(
    row: pd.Series,
    structured_columns: list[str],
    review_feature_columns: list[str],
) -> str:
    has_structured = any(to_bool(row.get(column, 0)) for column in structured_columns)
    has_review = any(to_bool(row.get(column, 0)) for column in review_feature_columns)
    if has_structured and has_review:
        return "structured feature matrix + review-derived Capterra support feature signals"
    if has_structured:
        return "structured feature matrix"
    if has_review:
        return "review-derived Capterra support feature signals"
    return "no positive structured or review-derived feature flags"


def _feature_evidence_quality(
    row: pd.Series,
    structured_columns: list[str],
    review_feature_columns: list[str],
) -> str:
    has_structured = any(to_bool(row.get(column, 0)) for column in structured_columns)
    has_review = any(to_bool(row.get(column, 0)) for column in review_feature_columns)
    if has_structured and has_review:
        return "mixed"
    if has_structured:
        return "structured"
    if has_review:
        return "review_derived"
    return "missing"


def _present_features(
    row: pd.Series,
    structured_columns: list[str],
    review_feature_columns: list[str],
) -> str:
    structured = [column for column in structured_columns if to_bool(row.get(column, 0))]
    review_derived = [column for column in review_feature_columns if to_bool(row.get(column, 0))]
    if structured and review_derived:
        return ", ".join([*structured, *[f"{column} (review-derived)" for column in review_derived]])
    if structured:
        return ", ".join(structured)
    if review_derived:
        return "review-derived support signals: " + ", ".join(review_derived)
    return "no positive structured or review-derived feature flags"


def ensure_data_ready(paths=PATHS, artifact_url: str | None = None) -> str:
    artifact_url = artifact_url if artifact_url is not None else RUNTIME.data_artifact_url
    if _has_processed_data(paths) and _has_chroma_index(paths):
        return "Processed data and Chroma index are available."

    if artifact_url:
        paths.artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = paths.artifact_dir / "saas-demo-data.zip"
        _download_file(artifact_url, artifact_path)
        _extract_artifact(artifact_path, paths)
        if _has_processed_data(paths) and _has_chroma_index(paths):
            return f"Loaded processed data artifact from {artifact_url}."

    if RUNTIME.production_mode:
        raise RuntimeError(
            "Production mode requires processed data and Chroma indexes. "
            "Set DATA_ARTIFACT_URL or package data before deployment."
        )

    return "Processed data artifact unavailable; demo fallback may be used."


def load_processed_or_demo(paths=PATHS) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    readiness = ensure_data_ready(paths)
    cache_key = _processed_cache_key(paths, readiness)
    cached = _PROCESSED_CACHE.get(cache_key)
    if cached is not None:
        products, reviews, notice = cached
        return products.copy(deep=False), reviews.copy(deep=False), notice

    if paths.product_master.exists() and paths.review_chunks.exists():
        products = pd.read_csv(paths.product_master)
        reviews = pd.read_csv(paths.review_chunks)
        for column in ["pricing_source_urls", "pricing_source_accessed"]:
            if column in products.columns:
                products[column] = products[column].fillna("")
        if "pricing_source_type" in products.columns:
            products["pricing_source_type"] = products["pricing_source_type"].fillna("missing")
        if "feature_evidence_quality" in products.columns:
            products["feature_evidence_quality"] = products["feature_evidence_quality"].fillna("missing")
        products = ensure_factgrid_columns(products)
        products = ensure_wikidata_columns(products)
        if "data_source" in products.columns and products["data_source"].eq("fictional_demo").all():
            result = (products, reviews, DEMO_NOTICE)
            _PROCESSED_CACHE[cache_key] = result
            return products.copy(deep=False), reviews.copy(deep=False), DEMO_NOTICE
        notice = "Using processed Kaggle/local dataset files. " + readiness
        result = (products, reviews, notice)
        _PROCESSED_CACHE[cache_key] = result
        return products.copy(deep=False), reviews.copy(deep=False), notice

    products, reviews, _ = build_product_master(
        demo_products(), demo_pricing(), demo_features(), demo_reviews()
    )
    products["data_source"] = "fictional_demo"
    reviews["data_source"] = "fictional_demo"
    result = (products, reviews, DEMO_NOTICE)
    _PROCESSED_CACHE[cache_key] = result
    return products.copy(deep=False), reviews.copy(deep=False), DEMO_NOTICE


def _processed_cache_key(paths=PATHS, readiness: str = "") -> tuple[object, ...]:
    return (
        str(paths.product_master.resolve()),
        _file_fingerprint(paths.product_master),
        str(paths.review_chunks.resolve()),
        _file_fingerprint(paths.review_chunks),
        str(paths.index_dir.resolve()),
        readiness,
        bool(RUNTIME.production_mode),
        RUNTIME.data_artifact_url,
    )


def _file_fingerprint(path: Path) -> tuple[bool, int, int]:
    if not path.exists():
        return (False, 0, 0)
    stat = path.stat()
    return (True, stat.st_size, stat.st_mtime_ns)


def _has_processed_data(paths=PATHS) -> bool:
    return paths.product_master.exists() and paths.review_chunks.exists()


def _has_chroma_index(paths=PATHS) -> bool:
    return (paths.index_dir / "chroma" / "chroma.sqlite3").exists()


def _download_file(url: str, target: Path, retries: int = 2, retry_delay: float = 2.0) -> None:
    attempts = max(0, retries) + 1
    tmp_target = target.with_name(f"{target.name}.tmp")

    for attempt in range(1, attempts + 1):
        try:
            if tmp_target.exists():
                tmp_target.unlink()
            with requests.get(url, stream=True, timeout=120) as response:
                response.raise_for_status()
                with tmp_target.open("wb") as file:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            file.write(chunk)
            tmp_target.replace(target)
            return
        except requests.RequestException as exc:
            if tmp_target.exists():
                tmp_target.unlink()
            if attempt == attempts or not _is_retryable_download_error(exc):
                raise
            time.sleep(retry_delay * attempt)


def _is_retryable_download_error(exc: requests.RequestException) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        return int(status_code) in DOWNLOAD_RETRYABLE_STATUS_CODES
    return isinstance(
        exc,
        (
            requests.ConnectionError,
            requests.Timeout,
            requests.ChunkedEncodingError,
            requests.ContentDecodingError,
        ),
    )


def _extract_artifact(artifact_path: Path, paths=PATHS) -> None:
    root = paths.processed_dir.parent.parent.resolve()
    with zipfile.ZipFile(artifact_path) as archive:
        for member in archive.infolist():
            destination = (root / member.filename).resolve()
            try:
                destination.relative_to(root)
            except ValueError:
                raise ValueError(f"Unsafe artifact path: {member.filename}")
        archive.extractall(root)


def write_processed_outputs(
    products: pd.DataFrame,
    reviews: pd.DataFrame,
    unmatched: pd.DataFrame,
    paths=PATHS,
) -> None:
    paths.processed_dir.mkdir(parents=True, exist_ok=True)
    products.to_csv(paths.product_master, index=False)
    reviews.to_csv(paths.review_chunks, index=False)
    unmatched.to_csv(paths.unmatched_records, index=False)


def _pricing_summary_frame(pricing: pd.DataFrame) -> pd.DataFrame:
    if pricing.empty:
        return pd.DataFrame(
            columns=[
                "normalized_name",
                "pricing_summary",
                "min_monthly_price",
                "has_free_plan",
                "has_enterprise_plan",
                "pricing_source_type",
                "pricing_source_urls",
                "pricing_source_accessed",
            ]
        )

    rows = []
    for normalized_name, group in pricing.groupby("normalized_name"):
        numeric_prices = group["monthly_price"].dropna()
        min_price = numeric_prices.min() if not numeric_prices.empty else pd.NA
        free = bool(group["free_plan"].fillna(False).any())
        enterprise = bool(group["enterprise_plan"].fillna(False).any())
        if pd.notna(min_price):
            unit_rows = group[group["monthly_price"] == min_price]["billing_unit"].dropna().astype(str)
            units = [unit for unit in unit_rows.unique() if unit]
        else:
            units = [unit for unit in group["billing_unit"].dropna().astype(str).unique() if unit]
        unit = units[0] if units else "month"
        parts = []
        if free:
            parts.append("free plan available")
        if pd.notna(min_price):
            parts.append(f"starts at ${float(min_price):g} per {unit}")
        if enterprise:
            parts.append("enterprise or quote-based plan available")
        parts.append(f"{len(group)} pricing plan record(s)")
        rows.append(
            {
                "normalized_name": normalized_name,
                "pricing_summary": "; ".join(parts),
                "min_monthly_price": min_price,
                "has_free_plan": free,
                "has_enterprise_plan": enterprise,
                "pricing_source_type": _pricing_source_type(group),
                "pricing_source_urls": _join_unique_text(group.get("source_url", pd.Series(dtype=str))),
                "pricing_source_accessed": _join_unique_text(
                    group.get("source_accessed", pd.Series(dtype=str))
                ),
            }
        )
    return pd.DataFrame(rows)


def _pricing_source_type(group: pd.DataFrame) -> str:
    values = {
        str(value).strip().lower()
        for value in group.get("pricing_source_type", pd.Series(dtype=str)).dropna()
        if str(value).strip()
    }
    if not values:
        return "missing"
    if len(values) > 1:
        return "mixed"
    return next(iter(values))


def _join_unique_text(values: pd.Series) -> str:
    unique: list[str] = []
    for value in values.dropna().astype(str):
        value = value.strip()
        if value and value.lower() != "nan" and value not in unique:
            unique.append(value)
    return "; ".join(unique)


def _review_summary_frame(reviews: pd.DataFrame) -> pd.DataFrame:
    if reviews.empty:
        return pd.DataFrame(
            columns=["normalized_name", "review_count", "average_review_rating"]
        )
    return (
        reviews.groupby("normalized_name")
        .agg(review_count=("review_text", "count"), average_review_rating=("rating", "mean"))
        .reset_index()
    )


def _product_doc(row: pd.Series) -> str:
    review_text = (
        f"Review coverage: {int(row.get('review_count', 0))} review(s), average review rating {row.get('average_review_rating')}"
        if int(row.get("review_count", 0) or 0) > 0
        else "Review coverage: no review evidence available"
    )
    return compact_text(
        [
            f"Product: {row.get('product_name', '')}",
            f"Vendor: {row.get('vendor_name', '')}",
            f"Category: {row.get('category', '')}",
            f"Description: {row.get('description', '')}",
            f"Market segment: {row.get('market_segment', '')}",
            f"Tags: {row.get('tags', '')}",
            f"Pricing summary: {row.get('pricing_summary', 'pricing unavailable')}",
            f"Pricing source: {row.get('pricing_source_type', 'missing')}",
            f"Pricing source URLs: {row.get('pricing_source_urls', '')}",
            f"Feature evidence source: {row.get('feature_evidence_source', '')}",
            f"Feature evidence quality: {row.get('feature_evidence_quality', '')}",
            f"Key features: {row.get('present_features', '')}",
            _factgrid_doc(row),
            _wikidata_doc(row),
            review_text,
        ]
    )


def _factgrid_doc(row: pd.Series) -> str:
    status = str(row.get("factgrid_status", "") or "").strip().lower()
    if not status or status == "missing":
        return ""
    return compact_text(
        [
            f"FactGrid status: {row.get('factgrid_status', '')}",
            f"FactGrid pricing: {row.get('factgrid_pricing_summary', '')}",
            f"FactGrid SLA: {row.get('factgrid_sla_summary', '')}",
            f"FactGrid API: {row.get('factgrid_api_summary', '')}",
            f"FactGrid source URLs: {row.get('factgrid_source_urls', '')}",
            f"FactGrid accessed: {row.get('factgrid_accessed', '')}",
            f"Pricing conflict flag: {row.get('pricing_conflict_flag', False)}",
        ]
    )


def _wikidata_doc(row: pd.Series) -> str:
    wikidata_id = str(row.get("wikidata_id", "") or "").strip()
    if not wikidata_id:
        return ""
    return compact_text(
        [
            f"Wikidata ID: {wikidata_id}",
            f"Wikidata label: {row.get('wikidata_label', '')}",
            f"Wikidata entity types: {row.get('wikidata_entity_types', '')}",
            f"Wikidata official website: {row.get('wikidata_official_website', '')}",
            f"Wikidata country: {row.get('wikidata_country', '')}",
            f"Wikidata inception: {row.get('wikidata_inception', '')}",
            f"Wikidata parent organization: {row.get('wikidata_parent_org', '')}",
            f"Wikidata stock ticker: {row.get('wikidata_stock_ticker', '')}",
            f"Wikidata source URL: {row.get('wikidata_source_url', '')}",
            f"Wikidata accessed: {row.get('wikidata_accessed', '')}",
        ]
    )


def _empty_products() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
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
        ]
    )


def _empty_pricing() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "product_name",
            "plan_name",
            "monthly_price",
            "billing_unit",
            "free_plan",
            "enterprise_plan",
            "pricing_notes",
            "pricing_source_type",
            "source_url",
            "source_accessed",
            "normalized_name",
        ]
    )


def _empty_features() -> pd.DataFrame:
    return pd.DataFrame(columns=["product_name", "normalized_name"])


def _empty_reviews() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "product_name",
            "review_title",
            "review_text",
            "pros",
            "cons",
            "rating",
            "review_date",
            "normalized_name",
        ]
    )


def _empty_review_chunks() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "product_name",
            "review_title",
            "review_text",
            "pros",
            "cons",
            "rating",
            "review_date",
            "normalized_name",
            "review_doc",
            "source_type",
        ]
    )
