from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from saas_copilot import retrieval


def test_tfidf_fallback_is_explicit_in_retriever_metadata(monkeypatch) -> None:
    monkeypatch.setattr(retrieval, "RUNTIME", SimpleNamespace(use_chroma=False))
    rows = pd.DataFrame(
        [
            {"product_name": "Alpha CRM", "product_doc": "CRM automation analytics reporting"},
            {"product_name": "Beta Desk", "product_doc": "Support ticketing knowledge base"},
        ]
    )

    results = retrieval.search_rows(
        rows,
        query="automation analytics",
        text_column="product_doc",
        top_k=1,
        collection_name="products",
        id_prefix="product",
    )

    assert results
    assert results[0].row["retrieval_backend"] == "tfidf"
