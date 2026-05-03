from __future__ import annotations

import pandas as pd


DEMO_NOTICE = (
    "Using bundled fictional demo data. Add Kaggle datasets and run scripts/ingest.py "
    "before using this for real software evaluation."
)


def demo_products() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "product_id": "demo-supportflow",
                "product_name": "SupportFlow",
                "vendor_name": "SupportFlow Labs",
                "category": "Customer Support",
                "description": "Ticketing, customer support automation, help center, chat, analytics, and integrations for growing support teams.",
                "website": "https://example.com/supportflow",
                "rating": 4.4,
                "market_segment": "SMB Mid-Market",
                "tags": "support, ticketing, automation, analytics",
            },
            {
                "product_id": "demo-deskpilot",
                "product_name": "DeskPilot",
                "vendor_name": "DeskPilot Systems",
                "category": "Customer Support",
                "description": "Affordable help desk for small teams with shared inboxes, automations, knowledge base, reporting, and API access.",
                "website": "https://example.com/deskvault",
                "rating": 4.1,
                "market_segment": "SMB",
                "tags": "help desk, support, small business",
            },
            {
                "product_id": "demo-opsdesk",
                "product_name": "OpsDesk",
                "vendor_name": "OpsDesk Software",
                "category": "IT Service Management",
                "description": "ITSM platform with incident management, workflow builder, SSO, reporting, enterprise controls, and approval workflows.",
                "website": "https://example.com/opsdesk",
                "rating": 4.0,
                "market_segment": "Enterprise",
                "tags": "itsm, service desk, workflow, sso",
            },
            {
                "product_id": "demo-growcrm",
                "product_name": "GrowCRM",
                "vendor_name": "GrowCRM Inc",
                "category": "CRM",
                "description": "CRM for startups with pipeline management, email automation, integrations, reporting, and collaboration tools.",
                "website": "https://example.com/growcrm",
                "rating": 4.3,
                "market_segment": "Startup SMB",
                "tags": "crm, sales, automation",
            },
            {
                "product_id": "demo-analyticscore",
                "product_name": "AnalyticsCore",
                "vendor_name": "AnalyticsCore",
                "category": "Analytics",
                "description": "Business intelligence and product analytics platform with dashboards, API access, reporting, SSO, and integrations.",
                "website": "https://example.com/analyticscore",
                "rating": 4.2,
                "market_segment": "Mid-Market Enterprise",
                "tags": "analytics, dashboards, reporting",
            },
        ]
    )


def demo_pricing() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "product_name": "SupportFlow",
                "plan_name": "Team",
                "monthly_price": 29,
                "billing_unit": "user/month",
                "free_plan": False,
                "enterprise_plan": False,
                "pricing_notes": "Team plan includes automations and reporting.",
            },
            {
                "product_name": "SupportFlow",
                "plan_name": "Enterprise",
                "monthly_price": None,
                "billing_unit": "custom",
                "free_plan": False,
                "enterprise_plan": True,
                "pricing_notes": "Enterprise pricing is quote-based.",
            },
            {
                "product_name": "DeskPilot",
                "plan_name": "Starter",
                "monthly_price": 12,
                "billing_unit": "user/month",
                "free_plan": True,
                "enterprise_plan": False,
                "pricing_notes": "Free plan has limited automation.",
            },
            {
                "product_name": "OpsDesk",
                "plan_name": "Business",
                "monthly_price": 65,
                "billing_unit": "agent/month",
                "free_plan": False,
                "enterprise_plan": False,
                "pricing_notes": "Business plan includes ITSM workflow builder and SSO.",
            },
            {
                "product_name": "GrowCRM",
                "plan_name": "Growth",
                "monthly_price": 24,
                "billing_unit": "user/month",
                "free_plan": False,
                "enterprise_plan": False,
                "pricing_notes": "Growth plan includes email automation and pipeline reporting.",
            },
            {
                "product_name": "AnalyticsCore",
                "plan_name": "Pro",
                "monthly_price": 49,
                "billing_unit": "user/month",
                "free_plan": False,
                "enterprise_plan": True,
                "pricing_notes": "Enterprise security controls are available on custom plans.",
            },
        ]
    )


def demo_features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "product_name": "SupportFlow",
                "automation": 1,
                "analytics": 1,
                "api": 1,
                "integrations": 1,
                "sso": 1,
                "ai_features": 1,
                "reporting": 1,
                "collaboration": 1,
                "workflow_builder": 0,
                "knowledge_base": 1,
            },
            {
                "product_name": "DeskPilot",
                "automation": 1,
                "analytics": 0,
                "api": 1,
                "integrations": 1,
                "sso": 0,
                "ai_features": 0,
                "reporting": 1,
                "collaboration": 1,
                "workflow_builder": 0,
                "knowledge_base": 1,
            },
            {
                "product_name": "OpsDesk",
                "automation": 1,
                "analytics": 1,
                "api": 1,
                "integrations": 1,
                "sso": 1,
                "ai_features": 0,
                "reporting": 1,
                "collaboration": 1,
                "workflow_builder": 1,
                "knowledge_base": 0,
            },
            {
                "product_name": "GrowCRM",
                "automation": 1,
                "analytics": 1,
                "api": 1,
                "integrations": 1,
                "sso": 0,
                "ai_features": 1,
                "reporting": 1,
                "collaboration": 1,
                "workflow_builder": 0,
                "knowledge_base": 0,
            },
            {
                "product_name": "AnalyticsCore",
                "automation": 0,
                "analytics": 1,
                "api": 1,
                "integrations": 1,
                "sso": 1,
                "ai_features": 1,
                "reporting": 1,
                "collaboration": 1,
                "workflow_builder": 0,
                "knowledge_base": 0,
            },
        ]
    )


def demo_reviews() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "product_name": "SupportFlow",
                "review_title": "Strong automation, setup takes planning",
                "review_text": "The automation builder reduced manual triage, but the initial setup required careful routing rules.",
                "pros": "Good automation, analytics, and integrations.",
                "cons": "Setup complexity for larger teams.",
                "rating": 4.0,
                "review_date": "2026-01-10",
            },
            {
                "product_name": "SupportFlow",
                "review_title": "Helpful reporting",
                "review_text": "Managers liked the dashboards and queue visibility, though advanced reports took time to configure.",
                "pros": "Dashboards and queue analytics are useful.",
                "cons": "Advanced reporting can be time-consuming.",
                "rating": 4.0,
                "review_date": "2026-02-04",
            },
            {
                "product_name": "DeskPilot",
                "review_title": "Low-cost help desk",
                "review_text": "The team adopted it quickly because the inbox and ticket views were simple.",
                "pros": "Affordable and easy to learn.",
                "cons": "Analytics are basic.",
                "rating": 4.0,
                "review_date": "2026-01-15",
            },
            {
                "product_name": "OpsDesk",
                "review_title": "Powerful but heavyweight",
                "review_text": "The workflow controls fit IT processes well, but nontechnical users found configuration complex.",
                "pros": "Strong workflow builder and enterprise controls.",
                "cons": "Configuration complexity and higher price.",
                "rating": 3.5,
                "review_date": "2026-02-20",
            },
            {
                "product_name": "GrowCRM",
                "review_title": "Good startup CRM",
                "review_text": "Sales teams liked pipeline visibility and email automation, but reporting needed cleanup.",
                "pros": "Pipeline management and automation.",
                "cons": "Reporting setup can be messy.",
                "rating": 4.0,
                "review_date": "2026-02-08",
            },
        ]
    )
