from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from saas_copilot.data_loader import load_processed_or_demo  # noqa: E402
from saas_copilot.enrichment import search_open_source_alternatives, wikidata_match_count  # noqa: E402
from saas_copilot.config import RUNTIME  # noqa: E402
from saas_copilot.llm import active_llm_available, active_llm_label  # noqa: E402
from saas_copilot.pipeline import run_analysis  # noqa: E402
from saas_copilot.retrieval import search_rows  # noqa: E402


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Run demo smoke checks.")
    parser.add_argument("--streamlit-url", default="http://localhost:8501")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Validate production deployment assumptions, including Groq configuration when selected.",
    )
    parser.add_argument(
        "--skip-web-health",
        action="store_true",
        help="Skip Streamlit/FastAPI health checks when no web server is running.",
    )
    args = parser.parse_args()

    checks = [
        check_processed_data(production=args.production),
        check_enrichment_data(),
        check_chroma_counts(),
        check_llm_provider(production=args.production),
        check_chroma_retrieval(),
        check_llm_generation(production=args.production),
        check_evaluation_results(),
    ]
    if not args.skip_web_health:
        checks.append(check_api(args.api_url) if args.production else check_streamlit(args.streamlit_url))

    mode = "Production" if args.production else "Local"
    print(f"\nSaaSScout {mode} Smoke Check")
    print("=" * 42)
    for check in checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"[{status}] {check.name}: {check.detail}")

    failed = [check for check in checks if not check.passed]
    if failed:
        print("\nResult: FAIL. Fix the failed checks before presenting the demo.")
        raise SystemExit(1)

    print(f"\nResult: PASS. The {mode.lower()} demo path is ready.")


def check_processed_data(production: bool = False) -> Check:
    try:
        products, reviews, notice = load_processed_or_demo()
        unmatched_path = ROOT / "data" / "processed" / "unmatched_records.csv"
        unmatched_count = len(pd.read_csv(unmatched_path)) if unmatched_path.exists() else -1
        is_demo = "fictional demo data" in notice.lower()
        passed = (
            len(products) >= 300
            and len(reviews) >= 4000
            and unmatched_count == 0
            and (not production or not is_demo)
        )
        return Check(
            "processed data",
            passed,
            f"products={len(products)}, reviews={len(reviews)}, unmatched={unmatched_count}, source={notice}",
        )
    except Exception as exc:
        return Check("processed data", False, f"{type(exc).__name__}: {exc}")


def check_chroma_counts() -> Check:
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(ROOT / "data" / "indexes" / "chroma"))
        product_count = client.get_collection("products").count()
        review_count = client.get_collection("reviews").count()
        try:
            alternative_count = client.get_collection("open_source_alternatives").count()
        except Exception:
            alternative_count = 0
        passed = product_count >= 300 and review_count >= 4000 and alternative_count >= 100
        return Check("Chroma indexes", passed, f"products={product_count}, reviews={review_count}, alternatives={alternative_count}")
    except Exception as exc:
        return Check("Chroma indexes", False, f"{type(exc).__name__}: {exc}")


def check_enrichment_data() -> Check:
    try:
        products, _, _ = load_processed_or_demo()
        factgrid_path = ROOT / "data" / "processed" / "factgrid_enrichment.csv"
        wikidata_path = ROOT / "data" / "processed" / "wikidata_vendor_facts.csv"
        alternatives_path = ROOT / "data" / "processed" / "open_source_alternatives.csv"
        factgrid = pd.read_csv(factgrid_path) if factgrid_path.exists() else pd.DataFrame()
        wikidata = pd.read_csv(wikidata_path) if wikidata_path.exists() else pd.DataFrame()
        alternatives = pd.read_csv(alternatives_path) if alternatives_path.exists() else pd.DataFrame()
        matched_factgrid = int(products.get("factgrid_status", pd.Series(dtype=str)).fillna("missing").ne("missing").sum())
        matched_wikidata = wikidata_match_count(products)
        passed = (
            len(factgrid) >= 30
            and len(wikidata) >= 25
            and len(alternatives) >= 100
            and matched_factgrid >= 5
            and matched_wikidata >= 25
        )
        return Check(
            "enrichment data",
            passed,
            (
                f"factgrid_rows={len(factgrid)}, factgrid_matches={matched_factgrid}, "
                f"wikidata_rows={len(wikidata)}, wikidata_matches={matched_wikidata}, "
                f"alternatives={len(alternatives)}"
            ),
        )
    except Exception as exc:
        return Check("enrichment data", False, f"{type(exc).__name__}: {exc}")


def check_llm_provider(production: bool = False) -> Check:
    provider = RUNTIME.llm_provider
    label = active_llm_label()
    if production and provider == "ollama":
        return Check(
            "LLM provider",
            False,
            "Ollama is local-only; set LLM_PROVIDER=groq for the hosted demo or template for no-key mode",
        )
    if production and provider == "groq" and not RUNTIME.groq_api_key:
        return Check("LLM provider", False, "LLM_PROVIDER=groq but GROQ_API_KEY is not configured")
    if provider == "template":
        return Check("LLM provider", True, "template fallback mode is configured")

    available = active_llm_available()
    if production and provider == "groq":
        passed = bool(RUNTIME.groq_api_key)
    else:
        passed = available
    return Check("LLM provider", passed, f"provider={provider}, label={label}, available={available}")


def check_chroma_retrieval() -> Check:
    try:
        products, reviews, _ = load_processed_or_demo()
        product_results = search_rows(
            products,
            "CRM automation workflow reporting",
            "product_doc",
            3,
            "products",
            "product",
        )
        review_subset = reviews[reviews["normalized_name"].isin(["zendesk"])]
        review_results = search_rows(
            review_subset,
            "pricing complaints setup complexity",
            "review_doc",
            3,
            "reviews",
            "review",
            where={"normalized_name": "zendesk"},
        )
        product_backends = {result.row.get("retrieval_backend") for result in product_results}
        review_backends = {result.row.get("retrieval_backend") for result in review_results}
        alternatives = search_open_source_alternatives("Find open-source alternatives to Airtable or Notion", top_k=3)
        alternative_backends = set(alternatives.get("Retriever", pd.Series(dtype=str)).dropna().astype(str))
        passed = "chroma" in product_backends and "chroma" in review_backends and "chroma" in alternative_backends
        return Check(
            "Chroma retrieval",
            passed,
            f"product_backends={sorted(product_backends)}, review_backends={sorted(review_backends)}, alternative_backends={sorted(alternative_backends)}",
        )
    except Exception as exc:
        return Check("Chroma retrieval", False, f"{type(exc).__name__}: {exc}")


def check_llm_generation(production: bool = False) -> Check:
    try:
        result = run_analysis(
            query="Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points.",
            category="Customer Support",
            compare_tools_text="Zendesk, Zoho Desk, Freshdesk",
            top_k=3,
            use_llm=True,
        )
        answer = result.answer.lower()
        pricing_missing_in_table = result.recommended_tools.get(
            "Pricing Summary", pd.Series(dtype=str)
        ).astype(str).str.contains("pricing unavailable", case=False, na=False).any()
        pricing_signal_ok = "pricing unavailable" in answer or not pricing_missing_in_table
        has_review_evidence = len(result.evidence_snippets) > 0
        provider_ok = True
        if production and RUNTIME.llm_provider == "groq":
            provider_ok = (
                result.llm_provider == "groq"
                or (result.llm_provider == "template" and bool(result.llm_warning))
            )
        passed = pricing_signal_ok and has_review_evidence and provider_ok
        return Check(
            "grounded LLM generation",
            passed,
            (
                f"provider={result.llm_provider}, model={result.llm_model}, status={result.llm_status}, "
                f"warning={result.llm_warning or 'none'}, confidence={result.confidence}, "
                f"evidence_snippets={len(result.evidence_snippets)}"
            ),
        )
    except Exception as exc:
        return Check("grounded LLM generation", False, f"{type(exc).__name__}: {exc}")


def check_evaluation_results() -> Check:
    path = ROOT / "data" / "processed" / "evaluation_results.csv"
    try:
        rows = pd.read_csv(path)
        passed = len(rows) == 15 and "product_retrievers" in rows.columns
        return Check("evaluation results", passed, f"rows={len(rows)}, path={path}")
    except Exception as exc:
        return Check("evaluation results", False, f"{type(exc).__name__}: {exc}")


def check_streamlit(base_url: str) -> Check:
    try:
        response = requests.get(f"{base_url.rstrip('/')}/_stcore/health", timeout=5)
        passed = response.status_code == 200
        return Check("Streamlit health", passed, f"url={base_url}, status={response.status_code}")
    except Exception as exc:
        return Check("Streamlit health", False, f"{type(exc).__name__}: {exc}")


def check_api(base_url: str) -> Check:
    try:
        response = requests.get(f"{base_url.rstrip('/')}/health", timeout=5)
        passed = response.status_code == 200 and response.json().get("status") == "ok"
        return Check("FastAPI health", passed, f"url={base_url}, status={response.status_code}")
    except Exception as exc:
        return Check("FastAPI health", False, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
