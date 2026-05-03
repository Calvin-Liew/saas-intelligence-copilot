from __future__ import annotations

import pandas as pd

from saas_copilot.normalizer import normalize_name
from saas_copilot.scoring import feature_columns, feature_display_name, map_required_features


def test_normalize_name_matches_join_contract() -> None:
    assert normalize_name(" Jira_Service-Management ") == "jira service management"


def test_feature_mapping_uses_synonyms_and_explicit_terms() -> None:
    products = pd.DataFrame(
        {
            "product_name": ["Example CRM"],
            "automation": [1],
            "analytics": [1],
            "api_access": [1],
            "workflow_builder": [0],
            "pricing_summary": ["starts at $20 per user"],
        }
    )

    available = feature_columns(products)
    mapped = map_required_features(
        "Need dashboard insights and workflow automation",
        "API access",
        available,
    )

    assert mapped == ["automation", "analytics", "api_access", "workflow_builder"]


def test_project_management_query_does_not_map_support_review_fields() -> None:
    available = [
        "automation",
        "reporting",
        "automated_ticket_routing",
        "reporting_and_analytics",
    ]

    mapped = map_required_features(
        "Find project management tools with automation and reporting.",
        "",
        available,
        category="Project Management",
    )

    assert mapped == ["automation", "reporting"]


def test_customer_support_query_can_map_support_review_fields() -> None:
    available = ["automation", "automated_ticket_routing"]

    mapped = map_required_features(
        "Which help desk tools support ticket routing?",
        "",
        available,
        category="Customer Support",
    )

    assert "automated_ticket_routing" in mapped
    assert feature_display_name("automated_ticket_routing") == "automated_ticket_routing (review-derived)"
