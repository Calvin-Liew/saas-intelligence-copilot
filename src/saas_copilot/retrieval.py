from __future__ import annotations

import math
import re
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Any

import pandas as pd

from .config import PATHS, RUNTIME
from .normalizer import normalize_name, split_terms


@dataclass(frozen=True)
class SearchResult:
    score: float
    row: dict[str, Any]


class TextRetriever:
    """Small local retrieval layer.

    The project requirements allow ChromaDB or FAISS for persistent vector search. For the
    Streamlit MVP this class keeps retrieval lightweight and deterministic with TF-IDF,
    while ingestion outputs stay compatible with later Chroma indexing.
    """

    def __init__(self, rows: pd.DataFrame, text_column: str):
        self.rows = rows.reset_index(drop=True).copy()
        self.text_column = text_column
        self.texts = self.rows.get(text_column, pd.Series(dtype=str)).fillna("").astype(str).tolist()

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if self.rows.empty:
            return []
        query = str(query or "").strip()
        if not query:
            return [
                SearchResult(score=1.0, row=row._asdict())
                for row in self.rows.head(top_k).itertuples(index=False)
            ]

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
            matrix = vectorizer.fit_transform([*self.texts, query])
            scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
        except Exception:
            scores = self._token_overlap_scores(query)

        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)[:top_k]
        return [
            SearchResult(score=float(score), row=self.rows.iloc[index].to_dict())
            for index, score in ranked
            if score > 0 or len(ranked) <= top_k
        ]

    def _token_overlap_scores(self, query: str) -> list[float]:
        query_terms = set(_tokens(query))
        scores = []
        for text in self.texts:
            text_terms = set(_tokens(text))
            if not query_terms or not text_terms:
                scores.append(0.0)
                continue
            scores.append(len(query_terms & text_terms) / math.sqrt(len(query_terms) * len(text_terms)))
        return scores


class ChromaRetriever:
    """Persistent embedding retriever backed by ChromaDB.

    Collections are built by scripts/build_chroma.py with ids such as product-0
    and review-42. Those numeric suffixes map back to the processed CSV row
    positions, so retrieval can return the full structured row for scoring.
    """

    def __init__(
        self,
        rows: pd.DataFrame,
        collection_name: str,
        id_prefix: str,
        index_path: Path | None = None,
    ):
        self.rows = rows.copy()
        self.collection_name = collection_name
        self.id_prefix = id_prefix
        self.index_path = index_path or (PATHS.index_dir / "chroma")
        self.allowed_ids = {f"{id_prefix}-{idx}" for idx in self.rows.index}
        self._row_by_id = {
            f"{id_prefix}-{idx}": row.to_dict() for idx, row in self.rows.iterrows()
        }

    def available(self) -> bool:
        if not RUNTIME.use_chroma or self.rows.empty or not self.index_path.exists():
            return False
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(self.index_path))
            collection = client.get_collection(self.collection_name)
            return collection.count() > 0
        except Exception:
            return False

    def search(
        self,
        query: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
        oversample: int = 12,
    ) -> list[SearchResult]:
        if self.rows.empty:
            return []
        query = str(query or "").strip()
        if not query:
            return [
                SearchResult(score=1.0, row=row.to_dict())
                for _, row in self.rows.head(top_k).iterrows()
            ]

        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(self.index_path))
            collection = client.get_collection(self.collection_name)
            n_results = min(collection.count(), max(top_k * oversample, top_k, 25))
            if n_results <= 0:
                return []
            result = self._query(collection, query, n_results, where)
        except Exception:
            return []

        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        rows: list[SearchResult] = []
        seen: set[str] = set()
        for item_id, distance in zip(ids, distances):
            if item_id in seen or item_id not in self.allowed_ids:
                continue
            row = self._row_by_id.get(item_id)
            if row is None:
                continue
            row["retrieval_backend"] = "chroma"
            rows.append(SearchResult(score=_distance_to_score(distance), row=row))
            seen.add(item_id)
            if len(rows) >= top_k:
                break
        return rows

    @staticmethod
    def _query(collection, query: str, n_results: int, where: dict[str, Any] | None):
        include = ["distances"]
        if where:
            try:
                return collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    where=where,
                    include=include,
                )
            except Exception:
                pass
        return collection.query(query_texts=[query], n_results=n_results, include=include)


def search_rows(
    rows: pd.DataFrame,
    query: str,
    text_column: str,
    top_k: int,
    collection_name: str,
    id_prefix: str,
    where: dict[str, Any] | None = None,
    oversample: int = 12,
) -> list[SearchResult]:
    chroma = ChromaRetriever(rows, collection_name, id_prefix)
    if chroma.available():
        results = chroma.search(query, top_k=top_k, where=where, oversample=oversample)
        if results:
            return results

    results = TextRetriever(rows, text_column).search(query, top_k=top_k)
    for result in results:
        result.row["retrieval_backend"] = "tfidf"
    return results


def apply_product_filters(
    products: pd.DataFrame,
    category: str | None = None,
    max_monthly_price: float | None = None,
    include_unknown_price: bool = True,
) -> pd.DataFrame:
    filtered = products.copy()
    if category and category != "All":
        filtered = filtered[
            filtered["category"].fillna("").astype(str).str.lower() == category.lower()
        ].copy()
    if max_monthly_price is not None:
        prices = pd.to_numeric(filtered.get("min_monthly_price"), errors="coerce")
        price_match = prices.le(max_monthly_price)
        if include_unknown_price:
            price_match = price_match | prices.isna()
        filtered = filtered[price_match].copy()
    return filtered


def match_product_names(products: pd.DataFrame, names: str | list[str]) -> pd.DataFrame:
    requested = split_terms(names) if isinstance(names, str) else names
    if not isinstance(requested, list):
        requested = []
    if not requested:
        return products.iloc[0:0].copy()

    normalized_lookup = {
        normalize_name(row["product_name"]): idx for idx, row in products.iterrows()
    }
    selected_indexes: list[int] = []
    for name in requested:
        normalized = normalize_name(name)
        if normalized in normalized_lookup:
            selected_indexes.append(normalized_lookup[normalized])
            continue

        contains_matches = [
            idx
            for product_key, idx in normalized_lookup.items()
            if normalized and (normalized in product_key or product_key in normalized)
        ]
        if contains_matches:
            selected_indexes.append(contains_matches[0])
            continue

        close = get_close_matches(normalized, normalized_lookup.keys(), n=1, cutoff=0.72)
        if close:
            selected_indexes.append(normalized_lookup[close[0]])

    if not selected_indexes:
        return products.iloc[0:0].copy()
    return products.loc[list(dict.fromkeys(selected_indexes))].copy()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _distance_to_score(distance: object) -> float:
    try:
        value = float(distance)
    except (TypeError, ValueError):
        return 0.0
    if value < 0:
        return 1.0
    return 1 / (1 + value)
