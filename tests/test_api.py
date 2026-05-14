from __future__ import annotations

import re
import sys
import threading
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from saas_copilot.api import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_api_caches():
    from saas_copilot import api as api_module

    api_module._STATUS_CACHE = None
    api_module._CHROMA_STATUS_CACHE = None
    api_module._OPTIONS_CACHE = None
    api_module._WARMUP_THREAD = None
    api_module._set_warmup_state("ready", "Test warmup is ready.")
    yield
    api_module._STATUS_CACHE = None
    api_module._CHROMA_STATUS_CACHE = None
    api_module._OPTIONS_CACHE = None
    api_module._WARMUP_THREAD = None
    api_module._set_warmup_state("idle", "Backend warmup has not started.")


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_stays_dependency_free(monkeypatch) -> None:
    from saas_copilot import api as api_module

    def fail_if_loaded():
        raise AssertionError("health should not load processed data")

    monkeypatch.setattr(api_module, "load_processed_or_demo", fail_if_loaded)
    test_client = TestClient(api_module.create_app())

    response = test_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_bootstrap_starts_background_warmup_without_inline_data_load(monkeypatch) -> None:
    from saas_copilot import api as api_module

    worker_started = threading.Event()
    release_worker = threading.Event()

    def fake_worker() -> None:
        worker_started.set()
        release_worker.wait(timeout=2)
        api_module._set_warmup_state("ready", "Test warmup is ready.")

    def fail_if_loaded():
        raise AssertionError("bootstrap should not load processed data inline")

    api_module._set_warmup_state("idle", "Backend warmup has not started.")
    monkeypatch.setattr(api_module, "_warmup_worker", fake_worker)
    monkeypatch.setattr(api_module, "load_processed_or_demo", fail_if_loaded)
    test_client = TestClient(api_module.create_app())

    response = test_client.get("/api/bootstrap")

    assert response.status_code == 200
    assert response.json() == {
        "ready": False,
        "warming": True,
        "error": "",
        "message": "Preparing product data, Chroma indexes, enrichment metadata, and options.",
    }
    assert worker_started.wait(timeout=1)
    release_worker.set()
    if api_module._WARMUP_THREAD is not None:
        api_module._WARMUP_THREAD.join(timeout=2)


def test_bootstrap_restarts_background_warmup_after_error(monkeypatch) -> None:
    from saas_copilot import api as api_module

    worker_started = threading.Event()
    release_worker = threading.Event()

    def fake_worker() -> None:
        worker_started.set()
        release_worker.wait(timeout=2)
        api_module._set_warmup_state("ready", "Recovered warmup is ready.")

    api_module._set_warmup_state("error", "Backend warmup failed: HTTPError.", "transient")
    monkeypatch.setattr(api_module, "_warmup_worker", fake_worker)
    test_client = TestClient(api_module.create_app())

    response = test_client.get("/api/bootstrap")

    assert response.status_code == 200
    assert response.json() == {
        "ready": False,
        "warming": True,
        "error": "",
        "message": "Preparing product data, Chroma indexes, enrichment metadata, and options.",
    }
    assert worker_started.wait(timeout=1)
    release_worker.set()
    if api_module._WARMUP_THREAD is not None:
        api_module._WARMUP_THREAD.join(timeout=2)
    assert api_module._warmup_snapshot()["state"] == "ready"


def test_warmup_worker_populates_status_and_options_once(monkeypatch) -> None:
    from saas_copilot import api as api_module

    calls = {"status": 0, "options": 0}

    def fake_status_payload():
        calls["status"] += 1
        api_module._STATUS_CACHE = (999999999.0, {"source": "test"})
        return {"source": "test"}

    def fake_options_payload():
        calls["options"] += 1
        api_module._OPTIONS_CACHE = (999999999.0, {"categories": ["All"]})
        return {"categories": ["All"]}

    monkeypatch.setattr(api_module, "_status_payload", fake_status_payload)
    monkeypatch.setattr(api_module, "_options_payload", fake_options_payload)
    api_module._set_warmup_state("warming", "Preparing test warmup.")

    api_module._warmup_worker()

    assert calls == {"status": 1, "options": 1}
    assert api_module._warmup_snapshot()["state"] == "ready"
    assert api_module._STATUS_CACHE is not None
    assert api_module._OPTIONS_CACHE is not None


def test_data_endpoints_return_fast_503_while_warming(monkeypatch) -> None:
    from saas_copilot import api as api_module

    def fail_if_loaded():
        raise AssertionError("warming endpoints should not load data inline")

    api_module._set_warmup_state("warming", "Preparing test warmup.")
    monkeypatch.setattr(api_module, "load_processed_or_demo", fail_if_loaded)
    test_client = TestClient(api_module.create_app())

    status_response = test_client.get("/api/status")
    options_response = test_client.get("/api/options")
    analyze_response = test_client.post(
        "/api/analyze",
        json={
            "query": "Compare Zendesk and Freshdesk.",
            "category": "Customer Support",
            "max_monthly_price": None,
            "required_features": [],
            "additional_required_features": "",
            "compare_tools": [],
            "additional_tool_names": "",
            "top_k": 3,
            "use_llm": False,
        },
    )

    for response in [status_response, options_response, analyze_response]:
        assert response.status_code == 503
        assert response.headers["retry-after"] == "3"
        assert response.json()["detail"] == "Preparing test warmup."


def test_data_endpoints_restart_warmup_after_error(monkeypatch) -> None:
    from saas_copilot import api as api_module

    worker_started = threading.Event()
    release_worker = threading.Event()

    def fake_worker() -> None:
        worker_started.set()
        release_worker.wait(timeout=2)
        api_module._set_warmup_state("ready", "Recovered warmup is ready.")

    def fail_if_loaded():
        raise AssertionError("error retry should start background warmup without inline data load")

    api_module._set_warmup_state("error", "Backend warmup failed: HTTPError.", "transient")
    monkeypatch.setattr(api_module, "_warmup_worker", fake_worker)
    monkeypatch.setattr(api_module, "load_processed_or_demo", fail_if_loaded)
    test_client = TestClient(api_module.create_app())

    response = test_client.get("/api/status")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "3"
    assert response.json()["detail"] == "Preparing product data, Chroma indexes, enrichment metadata, and options."
    assert worker_started.wait(timeout=1)
    release_worker.set()
    if api_module._WARMUP_THREAD is not None:
        api_module._WARMUP_THREAD.join(timeout=2)
    assert api_module._warmup_snapshot()["state"] == "ready"


def test_cors_allows_netlify_production_and_deploy_urls(monkeypatch) -> None:
    from saas_copilot import api as api_module

    monkeypatch.delenv("FRONTEND_ORIGIN_REGEX", raising=False)
    test_client = TestClient(api_module.create_app())
    for origin in [
        "https://saas-intelligence-copilot-calvi.netlify.app",
        "https://69f889f86e74e093ffbda506--saas-intelligence-copilot-calvi.netlify.app",
    ]:
        response = test_client.options(
            "/api/status",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_status_endpoint_reports_counts() -> None:
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["product_count"] >= 300
    assert data["review_count"] >= 4000
    assert "llm" in data
    assert "status" in data["llm"]
    assert "chroma" in data
    assert "enrichment" in data
    assert "factgrid_matches" in data["enrichment"]
    assert "wikidata_matches" in data["enrichment"]


def test_status_endpoint_uses_short_lived_cache(monkeypatch) -> None:
    from saas_copilot import api as api_module

    calls = {"data": 0, "chroma": 0, "enrichment": 0, "llm": 0}
    products = pd.DataFrame(
        [
            {"product_name": "Alpha CRM", "category": "Crm"},
            {"product_name": "Beta Desk", "category": "Customer Support"},
        ]
    )
    reviews = pd.DataFrame([{"product_name": "Beta Desk", "snippet": "Works well."}])

    def fake_load_processed_or_demo():
        calls["data"] += 1
        return products, reviews, "test data"

    def fake_chroma_status():
        calls["chroma"] += 1
        return {
            "ready": True,
            "product_count": 2,
            "review_count": 1,
            "alternatives_count": 0,
            "status": "Ready (2/1)",
        }

    def fake_enrichment_status(_products):
        calls["enrichment"] += 1
        return {
            "ready": True,
            "factgrid_matches": 1,
            "wikidata_matches": 1,
            "open_source_alternatives": 0,
            "status": "Ready (FactGrid 1 / Wikidata 1 / OSS 0)",
        }

    def fake_llm_available():
        calls["llm"] += 1
        return False

    monkeypatch.setattr(api_module, "load_processed_or_demo", fake_load_processed_or_demo)
    monkeypatch.setattr(api_module, "_chroma_status", fake_chroma_status)
    monkeypatch.setattr(api_module, "_enrichment_status", fake_enrichment_status)
    monkeypatch.setattr(api_module, "active_llm_available", fake_llm_available)
    monkeypatch.setattr(api_module, "active_llm_label", lambda: "Template")
    test_client = TestClient(api_module.create_app())

    first = test_client.get("/api/status")
    second = test_client.get("/api/status")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert calls == {"data": 1, "chroma": 1, "enrichment": 1, "llm": 1}


def test_chroma_status_uses_sqlite_fallback_after_client_error(monkeypatch, tmp_path) -> None:
    from saas_copilot import api as api_module

    class FailingClient:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("startup race")

    chroma_dir = tmp_path / "indexes" / "chroma"
    chroma_dir.mkdir(parents=True)
    db_path = chroma_dir / "chroma.sqlite3"
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            create table collections (id text primary key, name text);
            create table segments (id text primary key, scope text, collection text);
            create table embeddings (id integer primary key, segment_id text);
            insert into collections values ('products-id', 'products');
            insert into collections values ('reviews-id', 'reviews');
            insert into segments values ('products-meta', 'METADATA', 'products-id');
            insert into segments values ('reviews-meta', 'METADATA', 'reviews-id');
            """
        )
        conn.executemany(
            "insert into embeddings (segment_id) values (?)",
            [("products-meta",)] * 335 + [("reviews-meta",)] * 4899,
        )

    api_module._CHROMA_STATUS_CACHE = None
    monkeypatch.setattr(api_module, "PATHS", SimpleNamespace(index_dir=tmp_path / "indexes"))
    monkeypatch.setitem(sys.modules, "chromadb", SimpleNamespace(PersistentClient=FailingClient))

    recovered = api_module._chroma_status()

    assert recovered == {
        "ready": True,
        "product_count": 335,
        "review_count": 4899,
        "alternatives_count": 0,
        "status": "Ready (335/4899)",
    }
    api_module._CHROMA_STATUS_CACHE = None


def test_options_endpoint_includes_feature_labels() -> None:
    response = client.get("/api/options")
    assert response.status_code == 200
    data = response.json()
    assert "Customer Support" in data["categories"]
    assert any(feature["id"] == "ticket_creation_and_assignment" for feature in data["features"])
    assert any("review-derived" in feature["label"] for feature in data["features"])
    assert len(data["demo_presets"]) == 8
    assert data["demo_presets"][0]["label"] == "Support desk review risk"


def test_options_endpoint_uses_single_processed_data_load(monkeypatch) -> None:
    from saas_copilot import api as api_module

    calls = 0
    products = pd.DataFrame(
        [
            {
                "product_name": "Alpha CRM",
                "category": "Crm",
                "normalized_name": "alpha crm",
                "automation": 1,
            },
            {
                "product_name": "Beta Desk",
                "category": "Customer Support",
                "normalized_name": "beta desk",
                "ticket_creation_and_assignment": 1,
            },
        ]
    )

    def fake_load_processed_or_demo():
        nonlocal calls
        calls += 1
        return products, pd.DataFrame(), "test data"

    monkeypatch.setattr(api_module, "load_processed_or_demo", fake_load_processed_or_demo)
    test_client = TestClient(api_module.create_app())

    response = test_client.get("/api/options")

    assert response.status_code == 200
    assert calls == 1
    data = response.json()
    assert data["categories"] == ["All", "Crm", "Customer Support"]
    assert data["products"] == ["Alpha CRM", "Beta Desk"]
    assert any(feature["id"] == "automation" for feature in data["features"])


def test_options_endpoint_uses_short_lived_cache(monkeypatch) -> None:
    from saas_copilot import api as api_module

    calls = 0
    products = pd.DataFrame(
        [
            {
                "product_name": "Alpha CRM",
                "category": "Crm",
                "normalized_name": "alpha crm",
                "automation": 1,
            },
            {
                "product_name": "Beta Desk",
                "category": "Customer Support",
                "normalized_name": "beta desk",
                "ticket_creation_and_assignment": 1,
            },
        ]
    )

    def fake_load_processed_or_demo():
        nonlocal calls
        calls += 1
        return products, pd.DataFrame(), "test data"

    monkeypatch.setattr(api_module, "load_processed_or_demo", fake_load_processed_or_demo)
    test_client = TestClient(api_module.create_app())

    first = test_client.get("/api/options")
    second = test_client.get("/api/options")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert calls == 1


def test_analyze_endpoint_serializes_tables_and_provenance() -> None:
    response = client.post(
        "/api/analyze",
        json={
            "query": "Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points.",
            "category": "Customer Support",
            "max_monthly_price": None,
            "required_features": ["ticket_creation_and_assignment"],
            "additional_required_features": "",
            "compare_tools": ["Zendesk", "Zoho Desk", "Freshdesk"],
            "additional_tool_names": "",
            "top_k": 3,
            "use_llm": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["confidence"] == "medium"
    assert data["llm"]["status"] == "disabled"
    assert data["recommended_tools"]
    assert data["comparison_table"]
    assert "enterprise_metadata" in data
    assert "vendor_metadata" in data
    assert "open_source_alternatives" in data
    assert data["open_source_alternatives"] == []
    first = data["comparison_table"][0]
    assert first["Pricing Source"] == "supplemental"
    assert first["Feature Evidence Quality"] == "review_derived"
    assert not _contains_nan(data["comparison_table"])


def test_vendor_metadata_serializes_null_safe_values() -> None:
    response = client.post(
        "/api/analyze",
        json={
            "query": "Compare Salesforce, HubSpot, and Pipedrive for a growing sales team.",
            "category": "Crm",
            "max_monthly_price": None,
            "required_features": [],
            "additional_required_features": "",
            "compare_tools": ["Salesforce", "HubSpot", "Pipedrive"],
            "additional_tool_names": "",
            "top_k": 3,
            "use_llm": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "vendor_metadata" in data
    assert not _contains_nan(data["vendor_metadata"])


def test_open_source_alternatives_require_explicit_api_intent() -> None:
    response = client.post(
        "/api/analyze",
        json={
            "query": "Find open-source alternatives to Airtable or Notion for self-hosted knowledge management.",
            "category": "All",
            "max_monthly_price": None,
            "required_features": [],
            "additional_required_features": "",
            "compare_tools": [],
            "additional_tool_names": "",
            "top_k": 5,
            "use_llm": False,
        },
    )
    assert response.status_code == 200
    alternatives = response.json()["open_source_alternatives"]
    assert alternatives
    assert all(row["Evidence Type"] == "OpenAlternative CC0 directory evidence" for row in alternatives)
    assert not _contains_nan(alternatives)


def test_support_analysis_returns_review_themes_and_evidence_snippets() -> None:
    response = client.post(
        "/api/analyze",
        json={
            "query": "Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points.",
            "category": "Customer Support",
            "max_monthly_price": None,
            "required_features": ["ticket_creation_and_assignment"],
            "additional_required_features": "",
            "compare_tools": ["Zendesk", "Zoho Desk", "Freshdesk"],
            "additional_tool_names": "",
            "top_k": 3,
            "use_llm": False,
        },
    )
    assert response.status_code == 200
    data = response.json()

    assert data["review_themes"]
    assert data["evidence_snippets"]
    assert len(data["evidence_snippets"]) >= 3

    evidence_products = {item["product_name"] for item in data["evidence_snippets"]}
    assert evidence_products <= {"Zendesk", "Zoho Desk", "Freshdesk"}
    assert "Zendesk" in evidence_products

    backends = {item["retrieval_backend"] for item in data["evidence_snippets"]}
    assert backends <= {"chroma", "tfidf"}
    assert backends

    snippets = [item["snippet"] for item in data["evidence_snippets"]]
    assert all(snippet.strip() for snippet in snippets)
    assert any(
        marker in snippet
        for snippet in snippets
        for marker in ("Pros:", "Cons:", "Review:")
    )
    assert not any(
        re.search(r"\b(?:pros|cons|review):\s*nan\b", snippet, flags=re.IGNORECASE)
        for snippet in snippets
    )
    assert not any(
        re.search(
            r"\b(?:pros|cons|review):\s*(?:pros|cons|review):",
            snippet,
            flags=re.IGNORECASE,
        )
        for snippet in snippets
    )
    assert not any(
        re.search(r"\b(?:pros|cons|review):\S", snippet, flags=re.IGNORECASE)
        for snippet in snippets
    )

    coverage = [item["Review coverage"] for item in data["review_themes"]]
    assert any("retrieved snippet" in item for item in coverage)


def test_records_converts_nan_to_null() -> None:
    from saas_copilot.api import _records

    rows = _records(pd.DataFrame([{"value": float("nan")}]))
    assert rows == [{"value": None}]


def _contains_nan(value) -> bool:
    if isinstance(value, list):
        return any(_contains_nan(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_nan(item) for item in value.values())
    return isinstance(value, float) and pd.isna(value)
