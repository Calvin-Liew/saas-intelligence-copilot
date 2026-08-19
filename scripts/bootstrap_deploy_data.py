from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from saas_copilot.config import DataPaths, PATHS, RUNTIME  # noqa: E402
from saas_copilot.data_loader import install_data_artifact  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Install and validate production data during a deploy build.")
    parser.add_argument(
        "--target-root",
        type=Path,
        default=ROOT,
        help="Deployment root to populate. Defaults to the repository root.",
    )
    args = parser.parse_args()
    if not RUNTIME.data_artifact_url:
        raise SystemExit("DATA_ARTIFACT_URL is required during the production build.")

    paths = PATHS if args.target_root.resolve() == ROOT.resolve() else _paths_for_root(args.target_root)
    message = install_data_artifact(
        RUNTIME.data_artifact_url,
        paths=paths,
        expected_sha256=RUNTIME.data_artifact_sha256,
    )
    counts = validate_deploy_data(paths)
    print(message)
    print(f"product_master={paths.product_master}")
    print(f"review_chunks={paths.review_chunks}")
    print(f"chroma_index={paths.index_dir / 'chroma' / 'chroma.sqlite3'}")
    print(
        "validated_counts="
        f"products:{counts['products']},reviews:{counts['reviews']},"
        f"chroma_products:{counts['chroma_products']},chroma_reviews:{counts['chroma_reviews']}"
    )


def validate_deploy_data(paths: DataPaths) -> dict[str, int]:
    import chromadb
    import pandas as pd

    products = len(pd.read_csv(paths.product_master))
    reviews = len(pd.read_csv(paths.review_chunks))
    client = chromadb.PersistentClient(path=str(paths.index_dir / "chroma"))
    chroma_products = int(client.get_collection("products").count())
    chroma_reviews = int(client.get_collection("reviews").count())
    counts = {
        "products": products,
        "reviews": reviews,
        "chroma_products": chroma_products,
        "chroma_reviews": chroma_reviews,
    }
    if products < 300 or reviews < 4000 or chroma_products < 300 or chroma_reviews < 4000:
        raise RuntimeError(f"Deployment artifact failed minimum data validation: {counts}")
    return counts


def _paths_for_root(root: Path) -> DataPaths:
    data_dir = root.resolve() / "data"
    processed_dir = data_dir / "processed"
    return DataPaths(
        raw_dir=data_dir / "raw",
        processed_dir=processed_dir,
        index_dir=data_dir / "indexes",
        artifact_dir=data_dir / "artifacts",
        supplemental_dir=data_dir / "supplemental",
        product_master=processed_dir / "product_master.csv",
        review_chunks=processed_dir / "review_chunks.csv",
        unmatched_records=processed_dir / "unmatched_records.csv",
        supplemental_pricing=data_dir / "supplemental" / "support_tool_pricing.csv",
        factgrid_enrichment=processed_dir / "factgrid_enrichment.csv",
        wikidata_vendor_facts=processed_dir / "wikidata_vendor_facts.csv",
        open_source_alternatives=processed_dir / "open_source_alternatives.csv",
        enrichment_qa=processed_dir / "enrichment_qa.csv",
    )


if __name__ == "__main__":
    main()
