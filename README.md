# SaaSScout

## Overview

SaaSScout is a RAG-based software evaluation assistant for product analysts, procurement teams, and operators. It combines product metadata, pricing plans, feature flags, and review evidence to produce grounded SaaS recommendations, comparisons, and procurement-style next checks.

The app can run locally from Kaggle-processed files and Chroma indexes, or online from a packaged deployment artifact. Fictional demo data exists only as a development fallback.

## Problem

SaaS evaluation is fragmented across vendor pages, pricing sheets, review sites, and spreadsheets. This project helps shortlist tools by combining structured filters with semantic retrieval over product descriptions and review snippets.

## Dataset Stack

Expected raw inputs:

- SaaS Market Data 2026 SQLite: `comparedge/comparedge-saas-db-sqlite`
- SaaS and AI Tools Pricing Plans Database 2026: `comparedge/saas-pricing-plans-2026`
- SaaS Feature Matrix 2026: `comparedge/saas-feature-matrix-2026`
- Capterra Ticketsystem Reviews: `tobiasbueck/capterra-reviews`

Use `scripts/download_kaggle.py` to download through KaggleHub. If KaggleHub cannot access a dataset, the script falls back to the Kaggle CLI when it is installed and authenticated. You can also manually place downloaded files under `data/raw/`.

Supplemental data:

- `data/supplemental/support_tool_pricing.csv` adds source-backed pricing evidence for review-only support tools that are missing from the CompareEdge pricing table.
- Capterra support-review feature columns are aggregated into review-derived support feature signals and labeled separately from the structured CompareEdge feature matrix.

## Architecture

Data cleaning -> product-name normalization -> joins -> product and review documents -> Chroma embedding retrieval -> structured scoring/reranking -> grounded answer -> FastAPI backend -> React dashboard UI.

Core implementation:

- `src/saas_copilot/data_loader.py`: schema discovery, canonicalization, joins, QA unmatched records
- `src/saas_copilot/retrieval.py`: Chroma vector retrieval with TF-IDF fallback and metadata filtering
- `src/saas_copilot/scoring.py`: feature, pricing, review, category, and final scores
- `src/saas_copilot/pipeline.py`: query workflow and answer assembly
- `src/saas_copilot/api.py`: FastAPI service for Render deployment
- `frontend/`: Vite, React, TypeScript, and Tailwind UI for Netlify
- `app.py`: Streamlit local fallback while the React UI reaches final acceptance

## Features

- Natural-language SaaS discovery
- Side-by-side comparison for 2 to 4+ tools
- Required feature mapping against feature matrix columns
- Pricing-aware ranking with missing-data handling
- Review snippet retrieval and pain-point summaries
- Confidence level based on pricing, feature, and review coverage
- Provider-neutral grounded answer generation: Groq/Qwen online, Ollama/Qwen local, or deterministic template fallback

## Current Demo State

The local demo currently uses the downloaded Kaggle datasets and processed indexes:

- `335` products
- `4,899` review chunks
- `0` unmatched rows
- `29` categories
- `0` products with `pricing unavailable` after supplemental support-tool pricing enrichment
- Support-ticket feature gaps are filled with clearly labeled review-derived Capterra support feature signals
- Chroma collections for product and review retrieval
- Local Qwen via Ollama: `qwen2.5:1.5b`
- Online target: Groq `qwen/qwen3-32b`

## Run the Demo

For the React + FastAPI local demo, start the backend first:

```powershell
pip install -r requirements.txt
python scripts/download_kaggle.py; python scripts/ingest.py; python scripts/build_chroma.py; python scripts/evaluate.py
$env:PYTHONPATH="src"; uvicorn saas_copilot.api:app --reload --host 127.0.0.1 --port 8000
```

Then start the frontend in another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend calls `http://localhost:8000` by default.

## Recommended Demo Prompts

| Prompt | What it demonstrates |
|---|---|
| `Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points.` | Explicit comparison, supplemental pricing provenance, review-derived support feature signals |
| `Recommend a CRM for a small team that needs automation, workflow builder, reporting, and API integrations under $30.` | Pricing filters, structured feature scoring, and budget-aware ranking |
| `Find affordable project management platforms with automation, reporting analytics, templates, and API integrations.` | Chroma product discovery plus structured feature fit |
| `Compare Salesforce, HubSpot, and Pipedrive for a growing sales team that cares about automation, reporting, workflow builder, and pricing.` | Explicit vendor comparison with scorecard evidence |
| `Find website builders for a startup launch that need API access, analytics, templates, SEO tools, and custom domains.` | Metadata category filter plus feature-matrix matching |
| `Recommend a password manager with SSO, secure sharing, 2FA/MFA, breach alerts, and strong team security.` | Security-focused feature search with readable feature labels |
| `Create a procurement-style recommendation memo for choosing a customer support platform for a 200-person company.` | Memo-style answer, review snippets, and follow-up procurement checks |

## How to Run

Create an environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run the React app locally:

```powershell
$env:PYTHONPATH="src"
uvicorn saas_copilot.api:app --reload --host 127.0.0.1 --port 8000
cd frontend
npm install
npm run dev
```

Run the Streamlit fallback:

```powershell
streamlit run app.py
```

Download Kaggle data, then ingest:

```powershell
pip install -r requirements.txt
python scripts/download_kaggle.py
python scripts/ingest.py
```

Or point ingestion at explicit files:

```powershell
python scripts/ingest.py --products data/raw/saas_sqlite/file.sqlite --pricing data/raw/pricing/prices.csv --features data/raw/features/features.csv --reviews data/raw/reviews/reviews.csv
```

Optional persistent Chroma indexes:

```powershell
python scripts/build_chroma.py
```

Optional local LLM:

```powershell
$env:OLLAMA_MODEL="qwen2.5:1.5b"
streamlit run app.py
```

The default `.env.example` is configured for `qwen2.5:1.5b` through Ollama. If Ollama or the configured model is unavailable, the app uses a deterministic grounded response template.

For an online free-tier demo, configure the Render backend with Groq:

```toml
LLM_PROVIDER = "groq"
GROQ_API_KEY = "..."
GROQ_MODEL = "qwen/qwen3-32b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DATA_ARTIFACT_URL = "https://github.com/<user>/<repo>/releases/download/v1/saas-demo-data-v1.zip"
USE_CHROMA = "1"
PRODUCTION_MODE = "1"
FRONTEND_ORIGINS = "https://<netlify-site>.netlify.app"
```

Configure Netlify with:

```text
VITE_API_BASE_URL=https://<render-api>.onrender.com
```

Smoke test the full Chroma + Qwen path:

```powershell
python scripts/smoke_llm.py
```

Smoke test the full local demo:

```powershell
python scripts/smoke_all.py
```

## Production Deployment

The production path is a React frontend on Netlify and a FastAPI backend on Render. The backend should not download Kaggle datasets at startup. Instead, package the processed CSVs and Chroma index locally, upload the zip to a GitHub Release, and point `DATA_ARTIFACT_URL` at that release asset.

Build the deploy artifact:

```powershell
python scripts/evaluate.py
python scripts/build_chroma.py
python scripts/package_artifact.py
```

Upload `data/artifacts/saas-demo-data-v1.zip` to a GitHub Release.

Render backend:

- service config: `render.yaml`
- build command: `pip install -r requirements.txt`
- start command: `PYTHONPATH=src uvicorn saas_copilot.api:app --host 0.0.0.0 --port $PORT`
- required secrets: `GROQ_API_KEY`, `DATA_ARTIFACT_URL`, and `FRONTEND_ORIGINS`

Netlify frontend:

- project: `saas-intelligence-copilot-calvi`
- production URL: `https://saas-intelligence-copilot-calvi.netlify.app`
- config: `netlify.toml`
- build command: `npm run build`
- publish directory: `frontend/dist`
- required env var: `VITE_API_BASE_URL=https://<render-api>.onrender.com`

Frontend verification:

```powershell
cd frontend
npm run typecheck
npm test
npm run test:e2e
npm run build
```

Set the frontend API URL after the Render backend is live:

```powershell
netlify env:set VITE_API_BASE_URL https://<render-api>.onrender.com --context production --scope builds
npm run build --prefix frontend
netlify deploy --prod --dir frontend/dist
```

Production smoke check:

```powershell
python scripts/smoke_all.py --production --api-url https://<render-api>.onrender.com
Invoke-RestMethod https://<render-api>.onrender.com/health
```

Groq rate limits or API failures degrade to the grounded template response with a visible warning, so the app remains usable without inventing missing evidence.

## Evaluation

Run the prepared smoke queries:

```powershell
python scripts/evaluate.py
```

Results are written to `data/processed/evaluation_results.csv`. The starter query set lives in `data/evaluation/test_queries.csv`.

Review each result for:

- relevant retrieved tools
- correct metadata filtering
- review snippets tied to the right product
- clear missing-data statements
- no invented prices, features, or review claims

## Limitations

- Dataset freshness depends on the local Kaggle files you load.
- Pricing is not guaranteed current and should be verified with vendors.
- Product-name joins use normalization and may leave unmatched rows in `data/processed/unmatched_records.csv`.
- Missing reviews mean no linked review evidence, not positive sentiment.
- Support-ticket products from the Capterra dataset are review-only when they do not appear in the structured CompareEdge product universe, so pricing/features may depend on supplemental pricing and review-derived feature signals.
- Supplemental support-tool pricing is source-backed but still not real-time; quote-based and region-specific plans must be verified with vendors.
- Review-derived support feature signals are not the same as vendor-confirmed feature flags. They indicate positive feature evidence observed across Capterra review metadata and carry lower confidence than structured CompareEdge feature flags.
- The MVP does not perform legal, security, compliance, or ROI approval.

## Future Work

- LLM/API cost comparison mode
- Renewal-risk scoring
- Weighted vendor scorecards
- Exportable procurement memo
- Conversation memory for budget, company size, and must-have features
