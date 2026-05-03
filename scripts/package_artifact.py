from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from saas_copilot.config import PATHS  # noqa: E402


ARTIFACT_FILES = [
    PATHS.product_master,
    PATHS.review_chunks,
    PATHS.unmatched_records,
    PATHS.processed_dir / "evaluation_results.csv",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Package processed data and Chroma index for deployment.")
    parser.add_argument(
        "--out",
        default=str(PATHS.artifact_dir / "saas-demo-data-v1.zip"),
        help="Output zip path.",
    )
    args = parser.parse_args()

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)

    missing = [path for path in ARTIFACT_FILES if not path.exists()]
    chroma_dir = PATHS.index_dir / "chroma"
    if not chroma_dir.exists():
        missing.append(chroma_dir)
    if missing:
        raise SystemExit("Missing required artifact inputs: " + ", ".join(str(path) for path in missing))

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in ARTIFACT_FILES:
            archive.write(file_path, file_path.relative_to(ROOT))
        for file_path in chroma_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(ROOT))

    print(f"Wrote deployment artifact -> {output}")


if __name__ == "__main__":
    main()
