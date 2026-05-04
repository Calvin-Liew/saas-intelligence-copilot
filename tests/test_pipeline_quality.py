from __future__ import annotations

import pandas as pd

from saas_copilot import pipeline


def _products(feature_quality: str, feature_source: str, review_count: int = 10) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "product_name": "Example",
                "pricing_summary": "starts at $10 per user",
                "review_count": review_count,
                "feature_fit_score": 1.0,
                "feature_evidence_quality": feature_quality,
                "feature_evidence_source": feature_source,
                "automated_ticket_routing": 1,
                "automation": 1,
            }
        ]
    )


def test_review_derived_feature_match_adds_risk() -> None:
    risks = pipeline._risks(
        _products("review_derived", "review-derived Capterra support feature signals"),
        ["automated_ticket_routing"],
        "Using processed data.",
    )

    assert "Some feature evidence comes from review metadata, not vendor-confirmed feature flags." in risks


def test_review_derived_only_confidence_is_penalized() -> None:
    evidence = pd.DataFrame([{"snippet": "review evidence"}])
    structured = pipeline._confidence(_products("structured", "structured feature matrix"), evidence, ["automation"])
    review_derived = pipeline._confidence(
        _products("review_derived", "review-derived Capterra support feature signals"),
        evidence,
        ["automated_ticket_routing"],
    )

    assert structured == "high"
    assert review_derived == "medium"


def test_factgrid_feature_match_adds_risk() -> None:
    products = _products("mixed", "structured feature matrix; FactGrid enterprise metadata")
    products["matched_factgrid_features"] = "api (FactGrid API metadata)"

    risks = pipeline._risks(products, ["api"], "Using processed data.")

    assert "Some API evidence comes from FactGrid enterprise metadata, not the structured feature matrix." in risks
