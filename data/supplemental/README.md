# Supplemental Data

This folder contains small, source-backed enrichment files used when the core Kaggle datasets have known coverage gaps.

## `support_tool_pricing.csv`

Adds pricing-plan evidence for support/ticketing tools that appear in the Capterra review dataset but are not present in the CompareEdge pricing dataset:

- Zendesk
- Freshdesk
- Zoho Desk
- Jira Service Management
- ServiceNow
- OTRS

The file is intentionally narrow. Each row includes the product, plan name, normalized monthly price when a USD value is available, pricing notes, source URL, and access date. Quote-based or region-specific pricing is left blank instead of guessing.

The ingestion script appends this file to the raw pricing table before canonicalization.
