from __future__ import annotations

import re
import sys
from types import SimpleNamespace

import pandas as pd
from fastapi.testclient import TestClient

from saas_copilot.api import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_endpoint_reports_counts() -> None:
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["product_count"] >= 300
    assert data["review_count"] >= 4000
    assert "llm" in data
    assert "status" in data["llm"]
    assert "chroma" in data


def test_chroma_status_failure_cache_expires_quickly(monkeypatch) -> None:
    from saas_copilot import api as api_module

    class FailingClient:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("startup race")

    class ReadyCollection:
        def __init__(self, count: int) -> None:
            self._count = count

        def count(self) -> int:
            return self._count

    class ReadyClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_collection(self, name: str) -> ReadyCollection:
            return ReadyCollection(335 if name == "products" else 4899)

    api_module._CHROMA_STATUS_CACHE = None
    monkeypatch.setitem(sys.modules, "chromadb", SimpleNamespace(PersistentClient=FailingClient))

    failed = api_module._chroma_status()
    still_cached = api_module._chroma_status()

    assert failed["ready"] is False
    assert "RuntimeError" in failed["status"]
    assert still_cached["ready"] is False

    expires_at, cached_status = api_module._CHROMA_STATUS_CACHE
    api_module._CHROMA_STATUS_CACHE = (expires_at - api_module._CHROMA_FAILURE_TTL_SECONDS - 1, cached_status)
    monkeypatch.setitem(sys.modules, "chromadb", SimpleNamespace(PersistentClient=ReadyClient))

    recovered = api_module._chroma_status()

    assert recovered == {
        "ready": True,
        "product_count": 335,
        "review_count": 4899,
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
    assert len(data["demo_presets"]) == 7
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
    first = data["comparison_table"][0]
    assert first["Pricing Source"] == "supplemental"
    assert first["Feature Evidence Quality"] == "review_derived"
    assert not _contains_nan(data["comparison_table"])


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
