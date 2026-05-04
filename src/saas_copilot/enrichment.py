from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import requests

from .config import PATHS
from .normalizer import compact_text, normalize_name, to_bool
from .retrieval import search_rows


FACTGRID_API_BASE = "https://factgrid.org/api/v1"
WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
FACTGRID_COLUMNS = [
    "product_name",
    "normalized_name",
    "factgrid_slug",
    "factgrid_status",
    "factgrid_pricing_summary",
    "factgrid_starting_price_usd",
    "factgrid_sla_summary",
    "factgrid_api_summary",
    "factgrid_source_urls",
    "factgrid_accessed",
]
PRODUCT_FACTGRID_COLUMNS = [
    "factgrid_slug",
    "factgrid_status",
    "factgrid_pricing_summary",
    "factgrid_starting_price_usd",
    "factgrid_sla_summary",
    "factgrid_api_summary",
    "factgrid_source_urls",
    "factgrid_accessed",
    "pricing_conflict_flag",
]
WIKIDATA_COLUMNS = [
    "product_name",
    "normalized_name",
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
]
PRODUCT_WIKIDATA_COLUMNS = [
    column for column in WIKIDATA_COLUMNS if column not in {"product_name", "normalized_name"}
]
OPEN_SOURCE_COLUMNS = [
    "tool_name",
    "normalized_name",
    "category",
    "parent_category",
    "description",
    "license",
    "stars",
    "source_url",
    "source_repo",
    "open_source_doc",
]
QA_COLUMNS = ["source", "source_key", "status", "message"]

WIKIDATA_ALLOWED_ENTITY_TERMS = {
    "application software",
    "business",
    "chatbot",
    "collaborative software",
    "commercial organization",
    "company",
    "computing platform",
    "content management system",
    "customer relationship management software",
    "digital marketing company",
    "distributed collaboration software",
    "domain name registrar",
    "enterprise",
    "financial services",
    "free and open-source software",
    "generative artificial intelligence chatbot",
    "instant messaging",
    "large language model",
    "online service",
    "organization",
    "privately held company",
    "productivity software",
    "project management software",
    "proprietary software",
    "public company",
    "search engine",
    "service on internet",
    "software",
    "software as a service",
    "software company",
    "software developer",
    "software development",
    "technology company",
    "video-conferencing software",
    "virtual community",
    "web application",
    "web hosting service",
    "website",
    "website builder",
}
WIKIDATA_DISALLOWED_ENTITY_TERMS = {
    "album",
    "buurtschap",
    "city in the united states",
    "chinese constellation",
    "comics character",
    "desa",
    "district of ethiopia",
    "family name",
    "fictional human",
    "film",
    "ghost in a work of fiction",
    "houseware shop chain",
    "human",
    "musical group",
    "musical work/composition",
    "record label",
    "single",
    "sports season",
    "television character",
    "television program",
    "television station",
    "unincorporated community",
    "video game",
    "video game developer",
    "village",
    "wikimedia disambiguation page",
}

OPEN_SOURCE_INTENT_TERMS = (
    "open source",
    "open-source",
    "opensource",
    "oss",
    "self hosted",
    "self-hosted",
    "self host",
    "free alternative",
    "free replacement",
    "alternative to",
    "alternatives to",
    "replace",
    "replacement for",
    "vendor lock",
)

PROPRIETARY_ALTERNATIVE_HINTS: dict[str, dict[str, list[str]]] = {
    "airtable": {
        "categories": ["CRM & Sales", "Project & Work Management", "Forms & Surveys", "Note Taking & Knowledge Management"],
        "terms": ["database", "spreadsheet", "no-code", "workspace", "tables", "forms"],
    },
    "notion": {
        "categories": ["Note Taking & Knowledge Management", "Project & Work Management", "Collaboration & Communication"],
        "terms": ["wiki", "docs", "notes", "workspace", "knowledge", "project management"],
    },
    "zendesk": {
        "categories": ["Customer Support & Success", "Customer Communication Platforms"],
        "terms": ["support", "help desk", "ticketing", "chat", "customer service"],
    },
    "salesforce": {
        "categories": ["CRM & Sales"],
        "terms": ["crm", "sales", "pipeline", "customer relationship"],
    },
    "hubspot": {
        "categories": ["CRM & Sales", "Marketing & Customer Engagement"],
        "terms": ["crm", "sales", "marketing", "automation"],
    },
    "asana": {
        "categories": ["Project & Work Management", "Time & Task Management"],
        "terms": ["project", "task", "kanban", "team workflow"],
    },
    "monday": {
        "categories": ["Project & Work Management", "Time & Task Management"],
        "terms": ["project", "workflow", "work management", "kanban"],
    },
    "trello": {
        "categories": ["Project & Work Management", "Time & Task Management"],
        "terms": ["kanban", "boards", "tasks", "project"],
    },
}


def fetch_factgrid_enrichment(
    session: requests.Session | None = None,
    api_base: str = FACTGRID_API_BASE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    session = session or requests.Session()
    accessed = datetime.now(timezone.utc).date().isoformat()
    catalog_url = f"{api_base.rstrip('/')}/entities?include=all"
    response = session.get(catalog_url, timeout=60)
    response.raise_for_status()
    catalog = response.json()
    catalog_timestamp = _meta_timestamp(catalog) or accessed

    rows: list[dict[str, Any]] = []
    qa_rows: list[dict[str, str]] = []
    for entity in catalog.get("entities", []):
        slug = str(entity.get("slug", "")).strip()
        name = str(entity.get("name", "")).strip()
        if not slug or not name:
            continue
        row = _factgrid_catalog_row(entity, accessed=catalog_timestamp)
        verification_status = str(entity.get("verification_status", "")).upper()
        if verification_status == "VERIFIED":
            detail_url = f"{api_base.rstrip('/')}/entities/{slug}"
            try:
                detail_response = session.get(detail_url, timeout=60)
                detail_response.raise_for_status()
                row.update(_factgrid_detail_fields(detail_response.json(), accessed=catalog_timestamp))
                qa_rows.append(_qa("factgrid", slug, "fetched", "Detailed entity data fetched."))
            except requests.HTTPError as exc:
                qa_rows.append(_qa("factgrid", slug, "detail_failed", f"{type(exc).__name__}: {exc}"))
            except requests.RequestException as exc:
                qa_rows.append(_qa("factgrid", slug, "detail_failed", f"{type(exc).__name__}: {exc}"))
        else:
            qa_rows.append(_qa("factgrid", slug, "catalog_only", f"Detail skipped for status {verification_status or 'unknown'}."))
        rows.append(row)

    return (
        pd.DataFrame(rows, columns=FACTGRID_COLUMNS),
        pd.DataFrame(qa_rows, columns=QA_COLUMNS),
    )


def fetch_open_source_alternatives(
    session: requests.Session | None = None,
    readme_url: str = "https://raw.githubusercontent.com/piotrkulpinski/openalternative/main/README.md",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    session = session or requests.Session()
    response = session.get(readme_url, timeout=60)
    response.raise_for_status()
    frame = parse_openalternative_readme(response.text)
    qa = pd.DataFrame(
        [_qa("openalternative", readme_url, "fetched", f"Parsed {len(frame)} open-source alternative rows.")],
        columns=QA_COLUMNS,
    )
    return frame, qa


def fetch_wikidata_vendor_facts(
    products: pd.DataFrame,
    session: requests.Session | None = None,
    endpoint: str = WIKIDATA_SPARQL_ENDPOINT,
    chunk_size: int = 80,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    session = session or requests.Session()
    accessed = datetime.now(timezone.utc).date().isoformat()
    product_rows = _wikidata_product_rows(products)
    if not product_rows:
        return (
            pd.DataFrame(columns=WIKIDATA_COLUMNS),
            pd.DataFrame(
                [_qa("wikidata", "products", "missing_product_input", "No product names and websites were available for Wikidata matching.")],
                columns=QA_COLUMNS,
            ),
        )

    candidates_by_name: dict[str, list[dict[str, Any]]] = {}
    qa_rows: list[dict[str, str]] = []
    labels = [row["product_name"] for row in product_rows]
    for chunk in _chunks(labels, chunk_size):
        query = _wikidata_sparql_query(chunk)
        try:
            response = session.get(
                endpoint,
                params={"query": query, "format": "json"},
                headers={"User-Agent": "SaaSScout/0.1 Wikidata vendor facts enrichment"},
                timeout=90,
            )
            response.raise_for_status()
            bindings = response.json().get("results", {}).get("bindings", [])
        except requests.RequestException as exc:
            qa_rows.append(_qa("wikidata", ",".join(chunk[:3]), "fetch_failed", f"{type(exc).__name__}: {exc}"))
            continue

        for binding in bindings:
            candidate = _wikidata_candidate(binding, accessed)
            if not candidate["product_name"]:
                continue
            candidates_by_name.setdefault(candidate["product_name"], []).append(candidate)

    accepted_rows: list[dict[str, Any]] = []
    for product in product_rows:
        candidates = candidates_by_name.get(product["product_name"], [])
        accepted, rejected = _select_wikidata_candidate(product, candidates)
        if accepted:
            accepted_rows.append(accepted)
            qa_rows.append(_qa("wikidata", product["product_name"], "matched", f"Accepted {accepted['wikidata_id']} by official website domain."))
        elif not candidates:
            qa_rows.append(_qa("wikidata", product["product_name"], "no_candidate", "No exact-label Wikidata candidate returned."))
        else:
            qa_rows.append(_qa("wikidata", product["product_name"], "no_accepted_candidate", "No Wikidata candidate passed domain and entity-type checks."))
        qa_rows.extend(rejected)

    return (
        pd.DataFrame(accepted_rows, columns=WIKIDATA_COLUMNS),
        pd.DataFrame(qa_rows, columns=QA_COLUMNS),
    )


def parse_openalternative_readme(markdown: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    parent_category = ""
    category = ""
    item_pattern = re.compile(
        r"^- \[(?P<name>[^\]]+)\]\((?P<url>[^)]+)\) - (?P<description>.*?)(?P<meta>(?:\s+`[^`]+`)*)\s*$"
    )
    meta_pattern = re.compile(r"`([^`]+)`")

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("## ") and not line.startswith("### "):
            parent_category = line.removeprefix("## ").strip()
            category = ""
            continue
        if line.startswith("### "):
            category = line.removeprefix("### ").strip()
            continue
        match = item_pattern.match(line)
        if not match or not category:
            continue
        metadata = meta_pattern.findall(match.group("meta") or "")
        description = match.group("description").strip()
        license_value = next((item for item in metadata if not item.startswith("⭐")), "")
        stars = next((item.removeprefix("⭐").strip() for item in metadata if item.startswith("⭐")), "")
        tool_name = match.group("name").strip()
        source_url = match.group("url").strip()
        row = {
            "tool_name": tool_name,
            "normalized_name": normalize_name(tool_name),
            "category": category,
            "parent_category": parent_category,
            "description": description,
            "license": license_value,
            "stars": stars,
            "source_url": source_url,
            "source_repo": "https://github.com/piotrkulpinski/openalternative",
        }
        row["open_source_doc"] = _open_source_doc(row)
        rows.append(row)

    return pd.DataFrame(rows, columns=OPEN_SOURCE_COLUMNS)


def write_enrichment_outputs(
    factgrid: pd.DataFrame,
    alternatives: pd.DataFrame,
    qa: pd.DataFrame,
    wikidata: pd.DataFrame | None = None,
    paths=PATHS,
) -> None:
    paths.processed_dir.mkdir(parents=True, exist_ok=True)
    _coerce_columns(factgrid, FACTGRID_COLUMNS).to_csv(paths.factgrid_enrichment, index=False)
    _coerce_columns(wikidata if wikidata is not None else pd.DataFrame(), WIKIDATA_COLUMNS).to_csv(paths.wikidata_vendor_facts, index=False)
    _coerce_columns(alternatives, OPEN_SOURCE_COLUMNS).to_csv(paths.open_source_alternatives, index=False)
    _coerce_columns(qa, QA_COLUMNS).to_csv(paths.enrichment_qa, index=False)


def load_factgrid_enrichment(paths=PATHS) -> pd.DataFrame:
    if not paths.factgrid_enrichment.exists():
        return pd.DataFrame(columns=FACTGRID_COLUMNS)
    return _coerce_columns(pd.read_csv(paths.factgrid_enrichment), FACTGRID_COLUMNS)


def load_open_source_alternatives(paths=PATHS) -> pd.DataFrame:
    if not paths.open_source_alternatives.exists():
        return pd.DataFrame(columns=OPEN_SOURCE_COLUMNS)
    frame = _coerce_columns(pd.read_csv(paths.open_source_alternatives), OPEN_SOURCE_COLUMNS)
    frame["open_source_doc"] = frame.apply(
        lambda row: row["open_source_doc"] if _clean(row.get("open_source_doc")) else _open_source_doc(row),
        axis=1,
    )
    return frame


def load_wikidata_vendor_facts(paths=PATHS) -> pd.DataFrame:
    if not paths.wikidata_vendor_facts.exists():
        return pd.DataFrame(columns=WIKIDATA_COLUMNS)
    return _coerce_columns(pd.read_csv(paths.wikidata_vendor_facts), WIKIDATA_COLUMNS)


def ensure_factgrid_columns(products: pd.DataFrame) -> pd.DataFrame:
    out = products.copy()
    defaults: dict[str, Any] = {
        "factgrid_slug": "",
        "factgrid_status": "missing",
        "factgrid_pricing_summary": "no FactGrid pricing evidence",
        "factgrid_starting_price_usd": pd.NA,
        "factgrid_sla_summary": "no FactGrid SLA evidence",
        "factgrid_api_summary": "no FactGrid API evidence",
        "factgrid_source_urls": "",
        "factgrid_accessed": "",
        "pricing_conflict_flag": False,
    }
    for column, default in defaults.items():
        if column not in out.columns:
            out[column] = default
    out["factgrid_status"] = out["factgrid_status"].fillna("missing")
    out["factgrid_pricing_summary"] = out["factgrid_pricing_summary"].fillna("no FactGrid pricing evidence")
    out["factgrid_sla_summary"] = out["factgrid_sla_summary"].fillna("no FactGrid SLA evidence")
    out["factgrid_api_summary"] = out["factgrid_api_summary"].fillna("no FactGrid API evidence")
    out["factgrid_source_urls"] = out["factgrid_source_urls"].fillna("")
    out["factgrid_accessed"] = out["factgrid_accessed"].fillna("")
    out["pricing_conflict_flag"] = out["pricing_conflict_flag"].map(to_bool).fillna(False).astype(bool)
    return out


def ensure_wikidata_columns(products: pd.DataFrame) -> pd.DataFrame:
    out = products.copy()
    defaults = {
        "wikidata_id": "",
        "wikidata_label": "",
        "wikidata_entity_types": "",
        "wikidata_official_website": "",
        "wikidata_country": "",
        "wikidata_inception": "",
        "wikidata_parent_org": "",
        "wikidata_stock_ticker": "",
        "wikidata_source_url": "",
        "wikidata_accessed": "",
        "wikidata_match_method": "",
        "wikidata_match_confidence": "",
    }
    for column, default in defaults.items():
        if column not in out.columns:
            out[column] = default
        out[column] = out[column].fillna(default)
    return out


def apply_factgrid_enrichment(products: pd.DataFrame, factgrid: pd.DataFrame | None = None) -> pd.DataFrame:
    if products.empty:
        return ensure_factgrid_columns(products)
    factgrid = load_factgrid_enrichment() if factgrid is None else factgrid
    factgrid = _coerce_columns(factgrid, FACTGRID_COLUMNS)
    base = products.drop(columns=[column for column in PRODUCT_FACTGRID_COLUMNS if column in products.columns]).copy()
    if factgrid.empty:
        return ensure_factgrid_columns(base)

    enrichment = factgrid.drop_duplicates("normalized_name")[
        ["normalized_name", *[column for column in FACTGRID_COLUMNS if column not in {"product_name", "normalized_name"}]]
    ].copy()
    out = base.merge(enrichment, how="left", on="normalized_name")
    out = ensure_factgrid_columns(out)
    out["pricing_conflict_flag"] = out.apply(_pricing_conflict, axis=1).astype(bool)
    return out


def apply_wikidata_enrichment(products: pd.DataFrame, wikidata: pd.DataFrame | None = None) -> pd.DataFrame:
    if products.empty:
        return ensure_wikidata_columns(products)
    wikidata = load_wikidata_vendor_facts() if wikidata is None else wikidata
    wikidata = _coerce_columns(wikidata, WIKIDATA_COLUMNS)
    base = products.drop(columns=[column for column in PRODUCT_WIKIDATA_COLUMNS if column in products.columns]).copy()
    if wikidata.empty:
        return ensure_wikidata_columns(base)

    enrichment = wikidata.drop_duplicates("normalized_name")[
        ["normalized_name", *[column for column in WIKIDATA_COLUMNS if column not in {"product_name", "normalized_name"}]]
    ].copy()
    return ensure_wikidata_columns(base.merge(enrichment, how="left", on="normalized_name"))


def wants_open_source_alternatives(query: str) -> bool:
    text = normalize_name(query)
    return any(term in text for term in OPEN_SOURCE_INTENT_TERMS)


def search_open_source_alternatives(query: str, top_k: int = 5) -> pd.DataFrame:
    if not wants_open_source_alternatives(query):
        return pd.DataFrame(columns=_alternative_output_columns())
    alternatives = load_open_source_alternatives()
    if alternatives.empty:
        return pd.DataFrame(columns=_alternative_output_columns())

    hints = _query_hints(query)
    filtered = alternatives
    if hints["categories"]:
        category_match = alternatives["category"].isin(hints["categories"]) | alternatives["parent_category"].isin(hints["categories"])
        if category_match.any():
            filtered = alternatives[category_match].copy()

    enhanced_query = " ".join([query, *hints["terms"]]).strip()
    results = search_rows(
        filtered,
        query=enhanced_query,
        text_column="open_source_doc",
        top_k=top_k,
        collection_name="open_source_alternatives",
        id_prefix="alternative",
        oversample=16,
    )
    rows = []
    for result in results:
        row = result.row
        rows.append(
            {
                "Tool": row.get("tool_name", ""),
                "Category": row.get("category", ""),
                "Description": row.get("description", ""),
                "License": _clean(row.get("license", "")) or "Not listed",
                "Stars": _clean(row.get("stars", "")) or "Not listed",
                "Source": row.get("source_url", ""),
                "Evidence Type": "OpenAlternative CC0 directory evidence",
                "Retriever": row.get("retrieval_backend", ""),
                "Score": round(float(result.score), 3),
            }
        )
    return pd.DataFrame(rows, columns=_alternative_output_columns())


def factgrid_match_count(products: pd.DataFrame) -> int:
    if products.empty or "factgrid_status" not in products.columns:
        return 0
    return int(products["factgrid_status"].fillna("missing").ne("missing").sum())


def wikidata_match_count(products: pd.DataFrame) -> int:
    if products.empty or "wikidata_id" not in products.columns:
        return 0
    return int(products["wikidata_id"].fillna("").astype(str).str.strip().ne("").sum())


def normalize_domain(url: Any) -> str:
    text = _clean(url)
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    host = urlparse(text).netloc.lower().strip()
    if not host:
        return ""
    host = host.split("@")[-1].split(":")[0].removeprefix("www.")
    parts = [part for part in host.split(".") if part]
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "net", "ac", "gov"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def _wikidata_product_rows(products: pd.DataFrame) -> list[dict[str, str]]:
    if products.empty or "product_name" not in products.columns or "website" not in products.columns:
        return []
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, row in products.iterrows():
        product_name = _clean(row.get("product_name"))
        website = _clean(row.get("website"))
        domain = normalize_domain(website)
        normalized_name = normalize_name(product_name)
        if not product_name or not domain or normalized_name in seen:
            continue
        rows.append(
            {
                "product_name": product_name,
                "normalized_name": normalized_name,
                "website": website,
                "domain": domain,
            }
        )
        seen.add(normalized_name)
    return rows


def _wikidata_sparql_query(labels: list[str]) -> str:
    values = " ".join(_sparql_label(label) for label in labels)
    return f"""
SELECT ?item ?itemLabel
       (GROUP_CONCAT(DISTINCT ?instanceLabel; separator="; ") AS ?entity_types)
       (GROUP_CONCAT(DISTINCT STR(?website); separator="; ") AS ?official_websites)
       (SAMPLE(?countryLabel) AS ?country)
       (SAMPLE(?inception) AS ?inception)
       (SAMPLE(?parentLabel) AS ?parent_org)
       (GROUP_CONCAT(DISTINCT ?ticker; separator="; ") AS ?stock_ticker)
WHERE {{
  VALUES ?itemLabel {{ {values} }}
  ?item rdfs:label ?itemLabel .
  OPTIONAL {{ ?item wdt:P31 ?instance . }}
  OPTIONAL {{ ?item wdt:P856 ?website . }}
  OPTIONAL {{ ?item wdt:P17 ?country . }}
  OPTIONAL {{ ?item wdt:P571 ?inception . }}
  OPTIONAL {{
    {{ ?item wdt:P749 ?parent . }}
    UNION
    {{ ?item wdt:P127 ?parent . }}
  }}
  OPTIONAL {{ ?item wdt:P249 ?ticker . }}
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "en" .
    ?instance rdfs:label ?instanceLabel .
    ?country rdfs:label ?countryLabel .
    ?parent rdfs:label ?parentLabel .
  }}
}}
GROUP BY ?item ?itemLabel
LIMIT 500
"""


def _sparql_label(label: str) -> str:
    escaped = label.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"@en'


def _wikidata_candidate(binding: dict[str, Any], accessed: str) -> dict[str, Any]:
    item_url = _binding_value(binding, "item")
    wikidata_id = item_url.rsplit("/", 1)[-1] if item_url else ""
    official_websites = _split_joined_values(_binding_value(binding, "official_websites"))
    return {
        "product_name": _binding_value(binding, "itemLabel"),
        "normalized_name": normalize_name(_binding_value(binding, "itemLabel")),
        "wikidata_id": wikidata_id,
        "wikidata_label": _binding_value(binding, "itemLabel"),
        "wikidata_entity_types": _binding_value(binding, "entity_types"),
        "wikidata_official_website": "; ".join(official_websites),
        "wikidata_country": _binding_value(binding, "country"),
        "wikidata_inception": _date_only(_binding_value(binding, "inception")),
        "wikidata_parent_org": _binding_value(binding, "parent_org"),
        "wikidata_stock_ticker": _binding_value(binding, "stock_ticker"),
        "wikidata_source_url": f"https://www.wikidata.org/wiki/{wikidata_id}" if wikidata_id else item_url,
        "wikidata_accessed": accessed,
        "wikidata_match_method": "",
        "wikidata_match_confidence": "",
        "_domains": [normalize_domain(value) for value in official_websites if normalize_domain(value)],
    }


def _select_wikidata_candidate(
    product: dict[str, str],
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    rejected: list[dict[str, str]] = []
    domain_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        source_key = f"{product['product_name']}:{candidate.get('wikidata_id', '')}"
        domains = candidate.get("_domains", [])
        if not domains:
            rejected.append(_qa("wikidata", source_key, "missing_official_website", "Candidate has no official website claim."))
            continue
        if product["domain"] not in domains:
            rejected.append(_qa("wikidata", source_key, "no_domain_match", f"Local domain {product['domain']} did not match {', '.join(domains)}."))
            continue
        if not _wikidata_entity_allowed(candidate):
            rejected.append(_qa("wikidata", source_key, "disallowed_entity_type", candidate.get("wikidata_entity_types", "")))
            continue
        domain_candidates.append(candidate)

    if not domain_candidates:
        return None, rejected

    ranked = sorted(domain_candidates, key=_wikidata_candidate_score, reverse=True)
    top = ranked[0]
    if len(ranked) > 1:
        rejected.extend(
            _qa(
                "wikidata",
                f"{product['product_name']}:{candidate.get('wikidata_id', '')}",
                "ambiguous_multiple_candidates",
                f"Domain matched but lower-ranked than {top.get('wikidata_id', '')}.",
            )
            for candidate in ranked[1:]
        )
    accepted = {column: top.get(column, "") for column in WIKIDATA_COLUMNS}
    accepted["product_name"] = product["product_name"]
    accepted["normalized_name"] = product["normalized_name"]
    accepted["wikidata_match_method"] = "official_website_domain"
    accepted["wikidata_match_confidence"] = "high"
    if ";" in str(accepted.get("wikidata_official_website", "")):
        matched_sites = [
            value
            for value in _split_joined_values(accepted["wikidata_official_website"])
            if normalize_domain(value) == product["domain"]
        ]
        accepted["wikidata_official_website"] = matched_sites[0] if matched_sites else accepted["wikidata_official_website"]
    return accepted, rejected


def _wikidata_entity_allowed(candidate: dict[str, Any]) -> bool:
    types = {normalize_name(value) for value in _split_joined_values(candidate.get("wikidata_entity_types", ""))}
    if not types:
        return True
    has_allowed = any(
        allowed in entity_type or entity_type in allowed
        for entity_type in types
        for allowed in WIKIDATA_ALLOWED_ENTITY_TERMS
    )
    has_disallowed = any(
        disallowed in entity_type or entity_type in disallowed
        for entity_type in types
        for disallowed in WIKIDATA_DISALLOWED_ENTITY_TERMS
    )
    return has_allowed or not has_disallowed


def _wikidata_candidate_score(candidate: dict[str, Any]) -> tuple[int, int, str]:
    types = normalize_name(candidate.get("wikidata_entity_types", ""))
    company_score = 2 if any(term in types for term in ["company", "business", "enterprise", "organization"]) else 0
    software_score = 1 if any(term in types for term in ["software", "application", "online service", "website"]) else 0
    return company_score + software_score, len(str(candidate.get("wikidata_official_website", ""))), str(candidate.get("wikidata_id", ""))


def _binding_value(binding: dict[str, Any], key: str) -> str:
    return _clean((binding.get(key) or {}).get("value"))


def _split_joined_values(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip() and item.strip().lower() != "nan"]


def _date_only(value: str) -> str:
    text = _clean(value)
    return text[:10] if text else ""


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _factgrid_catalog_row(entity: dict[str, Any], accessed: str) -> dict[str, Any]:
    return {
        "product_name": _clean(entity.get("name")),
        "normalized_name": normalize_name(entity.get("name", "")),
        "factgrid_slug": _clean(entity.get("slug")),
        "factgrid_status": _clean(entity.get("verification_status")) or _clean(entity.get("trust_status")) or "catalog",
        "factgrid_pricing_summary": "no FactGrid pricing evidence",
        "factgrid_starting_price_usd": pd.NA,
        "factgrid_sla_summary": "no FactGrid SLA evidence",
        "factgrid_api_summary": "no FactGrid API evidence",
        "factgrid_source_urls": "",
        "factgrid_accessed": accessed,
    }


def _factgrid_detail_fields(detail: dict[str, Any], accessed: str) -> dict[str, Any]:
    core = detail.get("core_data") or {}
    pricing = core.get("pricing") or {}
    sla = core.get("sla") or {}
    api_limits = core.get("api_limits") or {}
    sources = core.get("data_sources") or {}
    source_urls = _join_unique(
        [
            sources.get("pricing_url"),
            sources.get("api_docs_url"),
            f"https://factgrid.org/entities/{detail.get('slug')}" if detail.get("slug") else "",
            f"https://factgrid.org/api/v1/entities/{detail.get('slug')}" if detail.get("slug") else "",
        ]
    )
    return {
        "factgrid_status": _clean(detail.get("verification_status")) or "VERIFIED",
        "factgrid_pricing_summary": _pricing_summary(pricing),
        "factgrid_starting_price_usd": _to_float(pricing.get("starting_price_usd")),
        "factgrid_sla_summary": _sla_summary(sla),
        "factgrid_api_summary": _api_summary(api_limits),
        "factgrid_source_urls": source_urls,
        "factgrid_accessed": _meta_timestamp(detail) or accessed,
    }


def _pricing_summary(pricing: dict[str, Any]) -> str:
    price = _clean(pricing.get("starting_price_usd"))
    period = _clean(pricing.get("billing_period")) or "month"
    context = _clean(pricing.get("pricing_context"))
    seats = _clean(pricing.get("min_seats_required"))
    if context:
        summary = f"FactGrid reports {context.rstrip('.')}"
        if seats:
            summary += f"; minimum seats {seats}"
        return summary
    if price:
        summary = f"FactGrid reports starting price ${price} per {period}"
        if seats:
            summary += f"; minimum seats {seats}"
        return summary
    return "no FactGrid pricing evidence"


def _sla_summary(sla: dict[str, Any]) -> str:
    uptime = _clean(sla.get("uptime_percentage"))
    tier = _clean(sla.get("tier_requirement"))
    sla_type = _clean(sla.get("sla_type"))
    if not any([uptime, tier, sla_type]):
        return "no FactGrid SLA evidence"
    return "; ".join(
        part
        for part in [
            f"uptime {uptime}%" if uptime else "",
            f"tier requirement {tier}" if tier else "",
            f"type {sla_type}" if sla_type else "",
        ]
        if part
    )


def _api_summary(api_limits: dict[str, Any]) -> str:
    system = _clean(api_limits.get("system_type"))
    limit = _clean(api_limits.get("rate_limit_value"))
    if not any([system, limit]):
        return "no FactGrid API evidence"
    return "; ".join(part for part in [f"system {system}" if system else "", f"rate limit {limit}" if limit else ""] if part)


def _pricing_conflict(row: pd.Series) -> bool:
    local_price = pd.to_numeric(pd.Series([row.get("min_monthly_price")]), errors="coerce").iloc[0]
    factgrid_price = pd.to_numeric(pd.Series([row.get("factgrid_starting_price_usd")]), errors="coerce").iloc[0]
    if pd.isna(local_price) or pd.isna(factgrid_price):
        return False
    if float(local_price) == 0.0 and to_bool(row.get("has_free_plan")) and float(factgrid_price) > 0:
        return False
    tolerance = max(1.0, abs(float(local_price)) * 0.05)
    return abs(float(local_price) - float(factgrid_price)) > tolerance


def _query_hints(query: str) -> dict[str, list[str]]:
    text = normalize_name(query)
    categories: list[str] = []
    terms: list[str] = []
    for product_name, hint in PROPRIETARY_ALTERNATIVE_HINTS.items():
        if product_name in text:
            categories.extend(hint["categories"])
            terms.extend(hint["terms"])
    return {
        "categories": list(dict.fromkeys(categories)),
        "terms": list(dict.fromkeys(terms)),
    }


def _alternative_output_columns() -> list[str]:
    return ["Tool", "Category", "Description", "License", "Stars", "Source", "Evidence Type", "Retriever", "Score"]


def _open_source_doc(row: pd.Series | dict[str, Any]) -> str:
    return compact_text(
        [
            f"Open-source tool: {row.get('tool_name', '')}",
            f"Category: {row.get('category', '')}",
            f"Parent category: {row.get('parent_category', '')}",
            f"Description: {row.get('description', '')}",
            f"License: {row.get('license', '')}",
            f"Stars: {row.get('stars', '')}",
            "Source: OpenAlternative CC0 GitHub repository",
        ]
    )


def _coerce_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = pd.NA
    return out[columns].copy()


def _qa(source: str, source_key: str, status: str, message: str) -> dict[str, str]:
    return {"source": source, "source_key": source_key, "status": status, "message": message}


def _meta_timestamp(payload: dict[str, Any]) -> str:
    timestamp = _clean((payload.get("_meta") or {}).get("timestamp"))
    if not timestamp:
        return ""
    return timestamp[:10]


def _clean(value: Any) -> str:
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


def _to_float(value: Any) -> Any:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return pd.NA
    return float(number)


def _join_unique(values: list[Any]) -> str:
    unique: list[str] = []
    for value in values:
        text = _clean(value)
        if text and text not in unique:
            unique.append(text)
    return "; ".join(unique)
