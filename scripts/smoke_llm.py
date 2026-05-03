from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from saas_copilot.llm import active_llm_available, active_llm_label  # noqa: E402
from saas_copilot.pipeline import run_analysis  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test Chroma retrieval plus active LLM generation.")
    parser.add_argument(
        "--query",
        default="Compare Zendesk, Zoho Desk, and Freshdesk for support ticketing pain points.",
    )
    parser.add_argument("--category", default="Customer Support")
    parser.add_argument("--tools", default="Zendesk, Zoho Desk, Freshdesk")
    args = parser.parse_args()

    print(f"llm_provider={active_llm_label()}")
    print(f"llm_available={active_llm_available()}")

    result = run_analysis(
        query=args.query,
        category=args.category,
        compare_tools_text=args.tools,
        top_k=3,
        use_llm=True,
    )
    print(f"llm_result={result.llm_provider}/{result.llm_model}/{result.llm_status}")
    if result.llm_warning:
        print(f"llm_warning={result.llm_warning}")
    print(f"confidence={result.confidence}")
    print("tools=" + ", ".join(result.recommended_tools["Product"].astype(str).tolist()))
    print("retrievers=" + ", ".join(result.recommended_tools["Retriever"].dropna().astype(str).unique()))
    if not result.evidence_snippets.empty:
        print(
            "review_retrievers="
            + ", ".join(result.evidence_snippets["retrieval_backend"].dropna().astype(str).unique())
        )
    print("\nANSWER\n" + result.answer[:3000])


if __name__ == "__main__":
    main()
