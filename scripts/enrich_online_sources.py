from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from saas_copilot.config import PATHS  # noqa: E402
from saas_copilot.data_loader import canonicalize_products, discover_raw_file, read_table  # noqa: E402
from saas_copilot.enrichment import (  # noqa: E402
    fetch_factgrid_enrichment,
    fetch_open_source_alternatives,
    fetch_wikidata_vendor_facts,
    write_enrichment_outputs,
)


def main() -> None:
    session = requests.Session()
    qa_frames: list[pd.DataFrame] = []

    print("Fetching FactGrid enterprise SaaS enrichment...")
    factgrid, factgrid_qa = fetch_factgrid_enrichment(session=session)
    qa_frames.append(factgrid_qa)

    print("Fetching OpenAlternative open-source alternatives...")
    alternatives, alternatives_qa = fetch_open_source_alternatives(session=session)
    qa_frames.append(alternatives_qa)

    products = _load_wikidata_product_source()
    print("Fetching Wikidata vendor facts...")
    wikidata, wikidata_qa = fetch_wikidata_vendor_facts(products=products, session=session)
    qa_frames.append(wikidata_qa)

    qa = pd.concat(qa_frames, ignore_index=True) if qa_frames else pd.DataFrame()
    write_enrichment_outputs(factgrid=factgrid, alternatives=alternatives, wikidata=wikidata, qa=qa)

    print(f"Wrote {len(factgrid)} FactGrid rows -> {PATHS.factgrid_enrichment}")
    print(f"Wrote {len(wikidata)} Wikidata vendor fact rows -> {PATHS.wikidata_vendor_facts}")
    print(f"Wrote {len(alternatives)} OpenAlternative rows -> {PATHS.open_source_alternatives}")
    print(f"Wrote {len(qa)} enrichment QA rows -> {PATHS.enrichment_qa}")


def _load_wikidata_product_source() -> pd.DataFrame:
    if PATHS.product_master.exists():
        products = pd.read_csv(PATHS.product_master)
        return products[[column for column in ["product_name", "normalized_name", "website"] if column in products.columns]].copy()

    product_path = discover_raw_file(PATHS.raw_dir, "products")
    if product_path is None:
        return pd.DataFrame(columns=["product_name", "normalized_name", "website"])
    return canonicalize_products(read_table(product_path, role="products"))[
        ["product_name", "normalized_name", "website"]
    ]


if __name__ == "__main__":
    main()
