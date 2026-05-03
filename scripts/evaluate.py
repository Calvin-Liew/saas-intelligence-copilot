from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from saas_copilot.pipeline import run_analysis  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retrieval/generation smoke evaluation.")
    parser.add_argument(
        "--queries",
        default="data/evaluation/test_queries.csv",
        help="CSV with query, category, required_features, compare_tools, max_monthly_price columns.",
    )
    parser.add_argument("--out", default="data/processed/evaluation_results.csv")
    args = parser.parse_args()

    queries = pd.read_csv(args.queries)
    rows = []
    for _, item in queries.iterrows():
        result = run_analysis(
            query=item.get("query", ""),
            category=item.get("category", "All") or "All",
            max_monthly_price=_optional_float(item.get("max_monthly_price")),
            required_features_text=item.get("required_features", ""),
            compare_tools_text=item.get("compare_tools", ""),
            top_k=_optional_int(item.get("top_k"), default=5),
            use_llm=False,
        )
        rows.append(
            {
                "query": item.get("query", ""),
                "confidence": result.confidence,
                "mapped_features": ", ".join(result.required_features),
                "top_tools": ", ".join(
                    result.recommended_tools.get("Product", pd.Series(dtype=str)).head(3).astype(str)
                ),
                "product_retrievers": ", ".join(
                    sorted(
                        result.recommended_tools.get("Retriever", pd.Series(dtype=str))
                        .dropna()
                        .astype(str)
                        .unique()
                    )
                ),
                "review_retrievers": ", ".join(
                    sorted(
                        result.evidence_snippets.get("retrieval_backend", pd.Series(dtype=str))
                        .dropna()
                        .astype(str)
                        .unique()
                    )
                ),
                "evidence_snippets": len(result.evidence_snippets),
                "answer_preview": result.answer[:500],
            }
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"Wrote evaluation results -> {out}")


def _optional_float(value: object) -> float | None:
    if pd.isna(value) or value == "":
        return None
    return float(value)


def _optional_int(value: object, default: int) -> int:
    if pd.isna(value) or value == "":
        return default
    return int(value)


if __name__ == "__main__":
    main()
