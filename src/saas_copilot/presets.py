from __future__ import annotations


DEMO_PRESETS = [
    {
        "label": "Support ticketing risk review",
        "query": "Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points.",
        "category": "Customer Support",
        "features": [],
        "tools": ["Zendesk", "Zoho Desk", "Freshdesk"],
        "max_price": None,
        "top_k": 3,
    },
    {
        "label": "Affordable project management shortlist",
        "query": "Find affordable project management tools with automation and reporting.",
        "category": "Project Management",
        "features": ["automation", "reporting"],
        "tools": [],
        "max_price": 25.0,
        "top_k": 5,
    },
    {
        "label": "CRM for small team",
        "query": "Recommend a CRM for a small team with automation and workflow builder under $30.",
        "category": "Crm",
        "features": ["automation", "workflow_builder"],
        "tools": [],
        "max_price": 30.0,
        "top_k": 5,
    },
    {
        "label": "Website builder feature fit",
        "query": "Find website builders with API access, analytics, and templates.",
        "category": "Website Builders",
        "features": ["api_access", "analytics", "templates"],
        "tools": [],
        "max_price": None,
        "top_k": 5,
    },
    {
        "label": "Password manager security",
        "query": "Recommend a password manager with SSO and advanced security.",
        "category": "Password Managers",
        "features": ["sso_integration", "advanced_security"],
        "tools": [],
        "max_price": None,
        "top_k": 5,
    },
]
