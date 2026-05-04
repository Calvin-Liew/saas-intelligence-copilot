from __future__ import annotations

import pandas as pd

from saas_copilot.enrichment import (
    apply_factgrid_enrichment,
    apply_wikidata_enrichment,
    fetch_wikidata_vendor_facts,
    normalize_domain,
    parse_openalternative_readme,
    search_open_source_alternatives,
    wants_open_source_alternatives,
)


def test_factgrid_merge_adds_enterprise_metadata() -> None:
    products = pd.DataFrame(
        [
            {
                "product_name": "Asana",
                "normalized_name": "asana",
                "min_monthly_price": 10,
            }
        ]
    )
    factgrid = pd.DataFrame(
        [
            {
                "product_name": "Asana",
                "normalized_name": "asana",
                "factgrid_slug": "asana",
                "factgrid_status": "VERIFIED",
                "factgrid_pricing_summary": "FactGrid reports starting price $10.2 per monthly",
                "factgrid_starting_price_usd": 10.2,
                "factgrid_sla_summary": "uptime 99.9%",
                "factgrid_api_summary": "system REST",
                "factgrid_source_urls": "https://factgrid.org/entities/asana",
                "factgrid_accessed": "2026-05-03",
            }
        ]
    )

    out = apply_factgrid_enrichment(products, factgrid)

    assert out.loc[0, "factgrid_status"] == "VERIFIED"
    assert out.loc[0, "factgrid_sla_summary"] == "uptime 99.9%"
    assert bool(out.loc[0, "pricing_conflict_flag"]) is False


def test_pricing_conflict_detection_flags_material_difference() -> None:
    products = pd.DataFrame(
        [{"product_name": "Asana", "normalized_name": "asana", "min_monthly_price": 10}]
    )
    factgrid = pd.DataFrame(
        [
            {
                "product_name": "Asana",
                "normalized_name": "asana",
                "factgrid_slug": "asana",
                "factgrid_status": "VERIFIED",
                "factgrid_pricing_summary": "FactGrid reports starting price $24 per monthly",
                "factgrid_starting_price_usd": 24,
                "factgrid_sla_summary": "uptime 99.9%",
                "factgrid_api_summary": "system REST",
                "factgrid_source_urls": "https://factgrid.org/entities/asana",
                "factgrid_accessed": "2026-05-03",
            }
        ]
    )

    out = apply_factgrid_enrichment(products, factgrid)

    assert bool(out.loc[0, "pricing_conflict_flag"]) is True


def test_openalternative_readme_parser_extracts_rows() -> None:
    markdown = """
## Business Software
### CRM & Sales
- [Twenty](https://openalternative.co/twenty) - Streamline customer relationships with modern CRM `AGPL-3.0` `⭐ 45K`
"""

    rows = parse_openalternative_readme(markdown)

    assert len(rows) == 1
    assert rows.loc[0, "tool_name"] == "Twenty"
    assert rows.loc[0, "category"] == "CRM & Sales"
    assert rows.loc[0, "license"] == "AGPL-3.0"
    assert rows.loc[0, "stars"] == "45K"
    assert "OpenAlternative" in rows.loc[0, "open_source_doc"]


def test_open_source_alternatives_require_explicit_intent(monkeypatch) -> None:
    alternatives = pd.DataFrame(
        [
            {
                "tool_name": "Twenty",
                "normalized_name": "twenty",
                "category": "CRM & Sales",
                "parent_category": "Business Software",
                "description": "Open-source CRM for sales teams.",
                "license": "AGPL-3.0",
                "stars": "45K",
                "source_url": "https://openalternative.co/twenty",
                "source_repo": "https://github.com/piotrkulpinski/openalternative",
                "open_source_doc": "Open-source CRM sales customer relationships",
            }
        ]
    )
    monkeypatch.setattr("saas_copilot.enrichment.load_open_source_alternatives", lambda: alternatives)

    assert not wants_open_source_alternatives("Recommend a CRM with automation")
    assert search_open_source_alternatives("Recommend a CRM with automation").empty

    results = search_open_source_alternatives("Find open-source alternatives to Salesforce")
    assert not results.empty
    assert results.loc[0, "Tool"] == "Twenty"


def test_normalize_domain_handles_www_and_paths() -> None:
    assert normalize_domain("https://www.salesforce.com/products/") == "salesforce.com"
    assert normalize_domain("https://salesforce.com") == "salesforce.com"
    assert normalize_domain("www.atlassian.com/software/jira") == "atlassian.com"


def test_wikidata_fetch_accepts_domain_verified_candidate_and_rejects_noise() -> None:
    products = pd.DataFrame(
        [
            {
                "product_name": "Salesforce",
                "normalized_name": "salesforce",
                "website": "https://www.salesforce.com",
            }
        ]
    )

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "results": {
                    "bindings": [
                        _wikidata_binding(
                            "Salesforce",
                            "Q941127",
                            "software company; business",
                            "https://www.salesforce.com",
                        ),
                        _wikidata_binding(
                            "Salesforce",
                            "Q110262554",
                            "Stack Exchange forum site",
                            "",
                        ),
                    ]
                }
            }

    class Session:
        def get(self, *args, **kwargs) -> Response:
            return Response()

    rows, qa = fetch_wikidata_vendor_facts(products, session=Session())

    assert len(rows) == 1
    assert rows.loc[0, "wikidata_id"] == "Q941127"
    assert rows.loc[0, "wikidata_match_method"] == "official_website_domain"
    assert "missing_official_website" in set(qa["status"])


def test_wikidata_fetch_rejects_label_only_noise_without_domain_match() -> None:
    products = pd.DataFrame(
        [{"product_name": "Asana", "normalized_name": "asana", "website": "https://asana.com"}]
    )

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "results": {
                    "bindings": [
                        _wikidata_binding(
                            "Asana",
                            "Q466797",
                            "postures in yoga",
                            "",
                        )
                    ]
                }
            }

    class Session:
        def get(self, *args, **kwargs) -> Response:
            return Response()

    rows, qa = fetch_wikidata_vendor_facts(products, session=Session())

    assert rows.empty
    assert "missing_official_website" in set(qa["status"])


def test_wikidata_merge_preserves_product_fields() -> None:
    products = pd.DataFrame(
        [
            {
                "product_name": "Salesforce",
                "normalized_name": "salesforce",
                "website": "https://www.salesforce.com",
                "pricing_summary": "starts at $25 per user",
            }
        ]
    )
    wikidata = pd.DataFrame(
        [
            {
                "product_name": "Salesforce",
                "normalized_name": "salesforce",
                "wikidata_id": "Q941127",
                "wikidata_label": "Salesforce",
                "wikidata_entity_types": "software company; business",
                "wikidata_official_website": "https://www.salesforce.com",
                "wikidata_country": "United States of America",
                "wikidata_inception": "1999-02-01",
                "wikidata_parent_org": "",
                "wikidata_stock_ticker": "CRM",
                "wikidata_source_url": "https://www.wikidata.org/wiki/Q941127",
                "wikidata_accessed": "2026-05-03",
                "wikidata_match_method": "official_website_domain",
                "wikidata_match_confidence": "high",
            }
        ]
    )

    out = apply_wikidata_enrichment(products, wikidata)

    assert out.loc[0, "pricing_summary"] == "starts at $25 per user"
    assert out.loc[0, "wikidata_id"] == "Q941127"
    assert out.loc[0, "wikidata_stock_ticker"] == "CRM"


def _wikidata_binding(label: str, qid: str, entity_types: str, website: str) -> dict:
    binding = {
        "item": {"value": f"https://www.wikidata.org/entity/{qid}"},
        "itemLabel": {"value": label},
        "entity_types": {"value": entity_types},
    }
    if website:
        binding["official_websites"] = {"value": website}
    return binding
