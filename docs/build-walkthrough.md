# SaaSScout Build Walkthrough

Use this as a personal end-to-end explanation of how the app was built, what each part does, and how the pieces connect.

## 1. Product Goal

SaaSScout was built as a RAG-based SaaS evaluation assistant. The goal was to answer questions like:

- "Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points."
- "Recommend a CRM for a small team under $30."
- "Find open-source alternatives to Airtable or Notion."

The important product decision was to avoid a generic chatbot answer. The app first grounds the answer in loaded datasets, review snippets, pricing evidence, feature flags, and public vendor metadata. The LLM can rewrite the answer, but the core recommendation is built from retrieved and scored evidence.

## 2. High-Level Architecture

The system flow is:

```text
Kaggle/raw data
  -> data ingestion and cleaning
  -> product-name normalization
  -> product/pricing/feature/review joins
  -> enrichment from supplemental pricing, FactGrid, Wikidata, and OpenAlternative
  -> product and review documents
  -> Chroma indexes with TF-IDF fallback
  -> scoring and reranking
  -> grounded answer assembly
  -> FastAPI backend
  -> React dashboard
  -> Netlify frontend and Render backend
  -> GitHub Actions production monitor
```

The key point is that retrieval, scoring, and provenance happen before generation. That is what keeps the app defensible for procurement-style analysis.

## 3. Data Layer

The app starts from four main raw data sources:

- CompareEdge SaaS market data SQLite
- CompareEdge SaaS pricing plans
- CompareEdge SaaS feature matrix
- Capterra ticket-system reviews

The first helper script is `scripts/download_kaggle.py`. It downloads the Kaggle datasets through KaggleHub, with a Kaggle CLI fallback if needed.

The main ingestion script is `scripts/ingest.py`. It:

- inspects source schemas
- normalizes product names
- joins product, pricing, feature, and review data
- builds a product master table
- builds review chunks for retrieval
- writes QA output for unmatched records

The main processed outputs are:

- `data/processed/product_master.csv`
- `data/processed/review_chunks.csv`
- `data/processed/unmatched_records.csv`

The code that owns most of this work lives in `src/saas_copilot/data_loader.py`.

## 4. Enrichment Layer

After the base dataset worked, extra evidence lanes were added so the app could explain recommendations better.

Supplemental pricing:

- File: `data/supplemental/support_tool_pricing.csv`
- Purpose: fills pricing gaps for support tools that appear in Capterra reviews but are missing from the structured pricing table.

Review-derived support features:

- Purpose: creates support-ticket feature signals from Capterra review metadata.
- Important caveat: these are labeled as review-derived, not vendor-confirmed structured features.

FactGrid:

- Script/code: `scripts/enrich_online_sources.py` and `src/saas_copilot/enrichment.py`
- Purpose: adds enterprise metadata such as status, pricing cross-checks, SLA/API notes, source URLs, and access dates.

Wikidata:

- Purpose: adds public vendor facts such as entity type, official website, country, inception, parent organization, and ticker.
- Matching rule: only joins when official website domains match local product website domains.

OpenAlternative:

- Purpose: adds open-source/self-hosted alternative discovery.
- Product behavior: normal SaaS queries are not polluted with open-source alternatives; alternatives appear when the query asks for open-source, self-hosted, or replacement-style options.

## 5. Retrieval Layer

The retrieval code lives in `src/saas_copilot/retrieval.py`.

The app uses separate Chroma collections for:

- products
- reviews
- open-source alternatives

The indexes are built with:

```powershell
python scripts/build_chroma.py
```

Chroma gives persistent semantic retrieval. If Chroma is unavailable, the app falls back to a lightweight TF-IDF retriever, so local development and degraded production still work.

Each retrieved row includes retriever metadata, so the UI can show whether evidence came from Chroma, TF-IDF, or direct product-name matching.

## 6. Scoring And Grounding

The scoring code lives in `src/saas_copilot/scoring.py`.

The app scores products using:

- feature fit
- pricing fit
- review coverage
- category match
- retrieval relevance
- evidence quality
- provenance risks

The full query workflow lives in `src/saas_copilot/pipeline.py`.

For each analysis request, the pipeline:

1. Loads processed products and reviews.
2. Selects candidate products by explicit tool names or semantic product search.
3. Maps requested features to feature columns.
4. Scores and reranks products.
5. Retrieves review snippets for the shortlisted products.
6. Loads enterprise metadata, vendor facts, and open-source alternatives when relevant.
7. Builds a deterministic grounded answer.
8. Optionally sends the grounded answer and evidence context to the configured LLM.

The deterministic template matters because the app can still answer when Groq, Ollama, or another model provider is unavailable.

## 7. LLM Layer

The LLM wrapper lives in `src/saas_copilot/llm.py`.

Supported paths:

- Groq/Qwen for the online demo
- Ollama/Qwen for local use
- grounded template fallback when the LLM is disabled or unavailable

The app does not rely on the LLM to invent recommendations. The model receives the grounded draft and retrieved evidence, then rewrites within that evidence. If the LLM fails, the frontend still receives a usable answer with a warning.

## 8. Backend API

The FastAPI app lives in `src/saas_copilot/api.py`.

Main routes:

- `GET /health`: simple uptime check
- `GET /api/status`: product count, review count, Chroma readiness, enrichment counts, and LLM status
- `GET /api/options`: categories, products, feature options, and demo presets
- `POST /api/analyze`: runs the full RAG/scoring pipeline

The backend also caches status/options checks so the UI and production monitor do not repeatedly hit expensive startup paths.

For local development:

```powershell
$env:PYTHONPATH="src"
uvicorn saas_copilot.api:app --reload --host 127.0.0.1 --port 8000
```

## 9. Frontend

The frontend lives in `frontend/`.

Stack:

- Vite
- React
- TypeScript
- Tailwind

The main app file is `frontend/src/App.tsx`. The API client is `frontend/src/api.ts`.

The UI was built around the workflow an analyst would use:

- choose a demo preset or write a custom query
- select category, budget, required features, and comparison tools
- run analysis
- inspect answer, scorecard, review evidence, enterprise metadata, vendor facts, and alternatives

The frontend also handles cold-start behavior. If Render is waking up or an analyze request times out, it keeps previous results and offers a template-mode retry.

For local development:

```powershell
cd frontend
npm install
npm run dev
```

## 10. Deployment

Production uses:

- Netlify for the React frontend
- Render for the FastAPI backend
- GitHub Release asset for the packaged processed data and Chroma index

The backend should not download Kaggle data at startup. Instead, the data is prepared locally and packaged:

```powershell
python scripts/enrich_online_sources.py
python scripts/ingest.py
python scripts/evaluate.py
python scripts/build_chroma.py
python scripts/package_artifact.py
```

The artifact is uploaded to a GitHub Release and Render receives the URL through `DATA_ARTIFACT_URL`.

Render uses `render.yaml`:

```text
PYTHONPATH=src uvicorn saas_copilot.api:app --host 0.0.0.0 --port $PORT
```

Netlify uses `netlify.toml`. It builds `frontend/` and proxies:

- `/api/*` to the Render backend
- `/health` to the Render backend

This same-origin proxy avoids browser CORS problems and lets production plus Netlify deploy previews use the same API path.

## 11. Monitoring And Reliability

The production monitor is `scripts/production_monitor.py`.

It checks the same path a real browser user hits:

- Netlify `/health`
- Netlify `/api/status`
- Netlify `/api/analyze` with `use_llm=false`

The GitHub Actions workflow is `.github/workflows/production-monitor.yml`. It runs on a schedule and can also be triggered manually.

The monitor reports the first failing layer as Netlify, Render, Chroma, enrichment, or analyze. It also has retry behavior for Render free-tier cold starts so temporary `502`, `503`, or `504` responses do not automatically look like real outages.

## 12. Testing

Backend and pipeline tests:

```powershell
python -m pytest tests
```

Frontend checks:

```powershell
cd frontend
npm run typecheck
npm test
npm run test:e2e
npm run build
```

Production smoke check:

```powershell
python scripts/production_monitor.py --site-url https://saas-intelligence-copilot-calvi.netlify.app --timeout 45 --retries 2 --retry-delay 8
```

## 13. Files To Remember

Core Python:

- `src/saas_copilot/data_loader.py`: data loading, joins, artifact bootstrap
- `src/saas_copilot/enrichment.py`: FactGrid, Wikidata, OpenAlternative, supplemental evidence
- `src/saas_copilot/retrieval.py`: Chroma and TF-IDF retrieval
- `src/saas_copilot/scoring.py`: feature/pricing/review scoring
- `src/saas_copilot/pipeline.py`: full analysis workflow
- `src/saas_copilot/llm.py`: LLM and template fallback
- `src/saas_copilot/api.py`: FastAPI routes

Scripts:

- `scripts/download_kaggle.py`: raw dataset download
- `scripts/enrich_online_sources.py`: online enrichment
- `scripts/ingest.py`: processed CSV build
- `scripts/build_chroma.py`: Chroma index build
- `scripts/evaluate.py`: prepared query evaluation
- `scripts/package_artifact.py`: production data artifact
- `scripts/smoke_all.py`: local or production smoke checks
- `scripts/production_monitor.py`: GitHub Actions production monitor

Frontend:

- `frontend/src/App.tsx`: main dashboard
- `frontend/src/api.ts`: API client and retry behavior
- `frontend/src/types.ts`: shared frontend response types
- `frontend/src/styles.css`: Tailwind component styling

Deployment:

- `render.yaml`: Render backend config
- `netlify.toml`: Netlify build and proxy config
- `.github/workflows/production-monitor.yml`: scheduled monitor

## 14. Demo Explanation

When explaining the project, use this order:

1. The problem is fragmented SaaS evaluation across pricing pages, reviews, feature matrices, and vendor metadata.
2. The app ingests and normalizes multiple datasets into one product/review workspace.
3. It enriches that workspace with pricing, enterprise metadata, public vendor facts, and open-source alternatives.
4. It retrieves relevant products and review snippets with Chroma, with TF-IDF fallback.
5. It scores tools before generation using feature, pricing, review, category, and evidence-quality signals.
6. It generates a grounded answer, scorecard, risks, and next checks.
7. The React UI exposes the evidence so users can inspect why a tool was recommended.
8. Production is deployed with Netlify, Render, a packaged data artifact, and GitHub Actions monitoring.

## 15. Main Tradeoffs

- Pricing is source-backed but not real-time, so vendor pricing still needs verification.
- Review-derived support features are useful but lower-confidence than vendor-confirmed structured features.
- Wikidata and FactGrid add context, but they are additive evidence and do not replace vendor verification.
- Render free-tier cold starts can cause intermittent timeouts, so the frontend and monitor include retry behavior.
- The app is a procurement research assistant, not a legal, compliance, security, or ROI approval system.
