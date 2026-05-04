# SaaSScout Demo Script

## 60-Second Walkthrough

1. Open the live demo: `https://saas-intelligence-copilot-calvi.netlify.app`.
2. Point out the status strip: product count, review chunks, Chroma, enrichment, and Groq/Qwen provider state.
3. Run the default support comparison prompt: `Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points.`
4. Show the answer tab, then the scorecard and evidence tabs.
5. Call out the key product idea: SaaSScout separates structured product/pricing data from review evidence, enterprise metadata, and public vendor facts.
6. Close with the reliability note: production is monitored through the same Netlify path users hit.

## 3-Minute Technical Walkthrough

1. Start with the architecture: Kaggle/local processed data, enrichment tables, Chroma retrieval, scoring, grounded generation, FastAPI, and React.
2. Run the support comparison prompt to show explicit tool comparison, supplemental pricing provenance, Capterra review snippets, and review-derived support feature caveats.
3. Run the CRM budget prompt: `Recommend a CRM for a small team that needs automation, workflow builder, reporting, and API integrations under $30.`
4. Show how the scorecard uses structured feature fit, pricing fit, confidence, retriever metadata, and vendor facts.
5. Run the open-source prompt: `Find open-source alternatives to Airtable or Notion for a team that wants self-hosted knowledge management.`
6. Explain that OpenAlternative is gated to open-source/self-hosted intent so normal SaaS recommendations are not polluted.
7. Mention production hardening: Netlify proxy, Render backend, packaged artifact startup, Groq fallback to template mode, and scheduled GitHub Actions monitoring.

## Recommended Demo Sequence

1. Support comparison: strongest review and evidence story.
2. CRM budget query: structured pricing and feature-fit story.
3. Open-source alternatives: separate evidence-lane story.
