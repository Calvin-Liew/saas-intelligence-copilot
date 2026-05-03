from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from saas_copilot.config import PATHS  # noqa: E402
from saas_copilot.data_loader import (  # noqa: E402
    build_product_master,
    discover_raw_file,
    read_table,
    write_processed_outputs,
)
from saas_copilot.demo_data import demo_features, demo_pricing, demo_products, demo_reviews  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build cleaned SaaS Copilot tables.")
    parser.add_argument("--products", default="", help="Product metadata file or SQLite database.")
    parser.add_argument("--pricing", default="", help="Pricing plans file.")
    parser.add_argument("--features", default="", help="Feature matrix file.")
    parser.add_argument("--reviews", default="", help="Review file.")
    parser.add_argument("--raw-dir", default=str(PATHS.raw_dir), help="Raw data directory.")
    parser.add_argument("--demo", action="store_true", help="Write bundled demo data to processed outputs.")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)

    using_demo = False
    if args.demo:
        using_demo = True
        products_raw = demo_products()
        pricing_raw = demo_pricing()
        features_raw = demo_features()
        reviews_raw = demo_reviews()
    else:
        product_path = _path_or_discover(args.products, raw_dir, "products")
        pricing_path = _path_or_discover(args.pricing, raw_dir, "pricing")
        features_path = _path_or_discover(args.features, raw_dir, "features")
        reviews_path = _path_or_discover(args.reviews, raw_dir, "reviews")

        if not any([product_path, pricing_path, features_path, reviews_path]):
            print("No raw files found. Writing bundled demo data instead.")
            using_demo = True
            products_raw = demo_products()
            pricing_raw = demo_pricing()
            features_raw = demo_features()
            reviews_raw = demo_reviews()
        else:
            products_raw = _load_or_empty(product_path, "products")
            pricing_raw = _load_or_empty(pricing_path, "pricing")
            features_raw = _load_or_empty(features_path, "features")
            reviews_raw = _load_or_empty(reviews_path, "reviews")

    pricing_raw = _append_supplemental_pricing(pricing_raw, using_demo)
    products, reviews, unmatched = build_product_master(
        products_raw, pricing_raw, features_raw, reviews_raw
    )
    if using_demo:
        products["data_source"] = "fictional_demo"
        reviews["data_source"] = "fictional_demo"
    write_processed_outputs(products, reviews, unmatched)

    print(f"Wrote {len(products)} products -> {PATHS.product_master}")
    print(f"Wrote {len(reviews)} review chunks -> {PATHS.review_chunks}")
    print(f"Wrote {len(unmatched)} unmatched QA rows -> {PATHS.unmatched_records}")


def _path_or_discover(value: str, raw_dir: Path, role: str) -> Path | None:
    if value:
        return Path(value)
    return discover_raw_file(raw_dir, role)


def _load_or_empty(path: Path | None, role: str) -> pd.DataFrame:
    if not path:
        print(f"No {role} file found; continuing with empty {role} table.")
        return pd.DataFrame()
    print(f"Loading {role}: {path}")
    return read_table(path, role=role)


def _append_supplemental_pricing(pricing: pd.DataFrame, using_demo: bool) -> pd.DataFrame:
    if using_demo or not PATHS.supplemental_pricing.exists():
        return pricing
    supplemental = pd.read_csv(PATHS.supplemental_pricing)
    if supplemental.empty:
        return pricing
    print(f"Loading supplemental pricing: {PATHS.supplemental_pricing}")
    return pd.concat([pricing, supplemental], ignore_index=True, sort=False)


if __name__ == "__main__":
    main()
