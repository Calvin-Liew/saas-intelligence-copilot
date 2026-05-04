from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from saas_copilot.config import PATHS  # noqa: E402
from saas_copilot.data_loader import load_processed_or_demo  # noqa: E402
from saas_copilot.enrichment import load_open_source_alternatives  # noqa: E402


def main() -> None:
    try:
        import chromadb
    except ImportError as exc:
        raise SystemExit("Install chromadb before building persistent indexes.") from exc

    products, reviews, _ = load_processed_or_demo()
    alternatives = load_open_source_alternatives()
    index_path = PATHS.index_dir / "chroma"
    index_path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(index_path))
    _upsert_collection(
        client,
        name="products",
        frame=products,
        id_prefix="product",
        text_column="product_doc",
        metadata_columns=["product_name", "category", "pricing_summary", "normalized_name"],
    )
    _upsert_collection(
        client,
        name="reviews",
        frame=reviews,
        id_prefix="review",
        text_column="review_doc",
        metadata_columns=["product_name", "rating", "normalized_name", "review_date"],
    )
    _upsert_collection(
        client,
        name="open_source_alternatives",
        frame=alternatives,
        id_prefix="alternative",
        text_column="open_source_doc",
        metadata_columns=["tool_name", "category", "parent_category", "license", "normalized_name"],
    )
    print(f"Built Chroma collections under {index_path}")


def _upsert_collection(
    client,
    name: str,
    frame: pd.DataFrame,
    id_prefix: str,
    text_column: str,
    metadata_columns: list[str],
) -> None:
    try:
        client.delete_collection(name)
    except Exception:
        pass
    collection = client.get_or_create_collection(name=name)
    if frame.empty:
        return
    docs = frame[text_column].fillna("").astype(str).tolist()
    ids = [f"{id_prefix}-{idx}" for idx in range(len(frame))]
    available_metadata = [column for column in metadata_columns if column in frame.columns]
    metadata_frame = (
        frame[available_metadata]
        .fillna("")
        .astype(str)
    )
    metadata_frame["row_id"] = [str(idx) for idx in range(len(frame))]
    metadatas = metadata_frame.to_dict("records")
    collection.upsert(ids=ids, documents=docs, metadatas=metadatas)


if __name__ == "__main__":
    main()
