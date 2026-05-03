from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


DATASETS = {
    "saas_sqlite": "comparedge/comparedge-saas-db-sqlite",
    "pricing": "comparedge/saas-pricing-plans-2026",
    "features": "comparedge/saas-feature-matrix-2026",
    "reviews": "tobiasbueck/capterra-reviews",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Kaggle datasets into data/raw.")
    parser.add_argument("--out", default="data/raw", help="Output directory.")
    parser.add_argument(
        "--only",
        choices=sorted(DATASETS),
        nargs="*",
        help="Optional subset of dataset keys to download.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = args.only or list(DATASETS)
    for key in keys:
        slug = DATASETS[key]
        target = out_dir / key
        target.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {slug} -> {target}")
        if not _download_with_kagglehub(slug, target):
            _download_with_kaggle_cli(slug, target)


def _download_with_kagglehub(slug: str, target: Path) -> bool:
    try:
        import kagglehub
    except ImportError:
        return False

    try:
        cache_path = Path(kagglehub.dataset_download(slug))
    except Exception as exc:
        print(f"KaggleHub download failed for {slug}: {exc}")
        return False

    for source in cache_path.rglob("*"):
        if source.is_file():
            relative = source.relative_to(cache_path)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return True


def _download_with_kaggle_cli(slug: str, target: Path) -> None:
    if not shutil.which("kaggle"):
        raise SystemExit(
            "KaggleHub failed and Kaggle CLI was not found. Install/configure Kaggle "
            "or download the dataset manually into data/raw."
        )

    subprocess.run(
        ["kaggle", "datasets", "download", "-d", slug, "-p", str(target), "--unzip"],
        check=True,
    )


if __name__ == "__main__":
    main()
