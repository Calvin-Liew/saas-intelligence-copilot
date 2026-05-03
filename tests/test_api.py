from __future__ import annotations

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


def test_options_endpoint_includes_feature_labels() -> None:
    response = client.get("/api/options")
    assert response.status_code == 200
    data = response.json()
    assert "Customer Support" in data["categories"]
    assert any(feature["id"] == "ticket_creation_and_assignment" for feature in data["features"])
    assert any("review-derived" in feature["label"] for feature in data["features"])
    assert len(data["demo_presets"]) == 5


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
