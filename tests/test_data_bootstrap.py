from __future__ import annotations

import hashlib
import shutil
import zipfile
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from saas_copilot import data_loader
from saas_copilot.config import DataPaths


def test_production_mode_does_not_silently_use_demo_data(monkeypatch, tmp_path) -> None:
    processed_dir = tmp_path / "processed"
    paths = DataPaths(
        raw_dir=tmp_path / "raw",
        processed_dir=processed_dir,
        index_dir=tmp_path / "indexes",
        artifact_dir=tmp_path / "artifacts",
        product_master=processed_dir / "product_master.csv",
        review_chunks=processed_dir / "review_chunks.csv",
        unmatched_records=processed_dir / "unmatched_records.csv",
    )
    monkeypatch.setattr(
        data_loader,
        "RUNTIME",
        SimpleNamespace(data_artifact_url="", production_mode=True),
    )

    with pytest.raises(RuntimeError, match="Production mode requires processed data"):
        data_loader.load_processed_or_demo(paths)


def test_production_mode_does_not_download_artifact_at_runtime(monkeypatch, tmp_path) -> None:
    processed_dir = tmp_path / "processed"
    paths = DataPaths(
        raw_dir=tmp_path / "raw",
        processed_dir=processed_dir,
        index_dir=tmp_path / "indexes",
        artifact_dir=tmp_path / "artifacts",
        product_master=processed_dir / "product_master.csv",
        review_chunks=processed_dir / "review_chunks.csv",
        unmatched_records=processed_dir / "unmatched_records.csv",
    )
    monkeypatch.setattr(
        data_loader,
        "RUNTIME",
        SimpleNamespace(
            data_artifact_url="https://example.test/artifact.zip",
            data_artifact_sha256="",
            production_mode=True,
            allow_runtime_artifact_bootstrap=False,
        ),
    )
    monkeypatch.setattr(
        data_loader,
        "_download_file",
        lambda *_args, **_kwargs: pytest.fail("runtime must not download deployment data"),
    )

    with pytest.raises(RuntimeError, match="installed during the build step"):
        data_loader.ensure_data_ready(paths)


def test_supplemental_pricing_preserves_source_metadata() -> None:
    pricing = pd.DataFrame(
        [
            {
                "product_name": "Zendesk",
                "plan_name": "Support Team",
                "monthly_price": 19,
                "billing_unit": "agent/mo",
                "source_url": "https://www.zendesk.com/pricing/",
                "source_accessed": "2026-05-02",
            }
        ]
    )

    out = data_loader.canonicalize_pricing(pricing)

    assert out.loc[0, "pricing_source_type"] == "supplemental"
    assert out.loc[0, "source_url"] == "https://www.zendesk.com/pricing/"


def test_download_file_retries_retryable_http_errors(monkeypatch, tmp_path) -> None:
    attempts = 0

    class FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def __enter__(self):
            return self

        def __exit__(self, *args) -> bool:
            return False

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                error = requests.HTTPError(f"status={self.status_code}")
                error.response = self
                raise error

        def iter_content(self, chunk_size: int):
            return [b"demo-artifact"]

    def fake_get(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        return FakeResponse(503 if attempts == 1 else 200)

    monkeypatch.setattr(data_loader.requests, "get", fake_get)
    monkeypatch.setattr(data_loader.time, "sleep", lambda seconds: None)
    target = tmp_path / "artifact.zip"

    data_loader._download_file("https://example.test/artifact.zip", target, retries=1, retry_delay=0)

    assert attempts == 2
    assert target.read_bytes() == b"demo-artifact"
    assert not (tmp_path / "artifact.zip.tmp").exists()


def test_artifact_checksum_mismatch_is_rejected(tmp_path) -> None:
    target = tmp_path / "artifact.zip"
    target.write_bytes(b"unexpected")

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        data_loader._verify_file_sha256(target, "0" * 64)


def test_install_data_artifact_verifies_extracts_and_removes_archive(monkeypatch, tmp_path) -> None:
    source = tmp_path / "source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("data/processed/product_master.csv", "product_name\nExample\n")
        archive.writestr("data/processed/review_chunks.csv", "product_name,review_text\nExample,Good\n")
        archive.writestr("data/indexes/chroma/chroma.sqlite3", b"sqlite-placeholder")
    expected_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

    deploy_root = tmp_path / "deploy"
    processed_dir = deploy_root / "data" / "processed"
    paths = DataPaths(
        raw_dir=deploy_root / "data" / "raw",
        processed_dir=processed_dir,
        index_dir=deploy_root / "data" / "indexes",
        artifact_dir=deploy_root / "data" / "artifacts",
        product_master=processed_dir / "product_master.csv",
        review_chunks=processed_dir / "review_chunks.csv",
        unmatched_records=processed_dir / "unmatched_records.csv",
    )

    def fake_download(_url, target, **_kwargs):
        shutil.copyfile(source, target)

    monkeypatch.setattr(data_loader, "_download_file", fake_download)

    message = data_loader.install_data_artifact(
        "https://example.test/artifact.zip",
        paths=paths,
        expected_sha256=expected_sha256,
    )

    assert message.startswith("Installed processed data")
    assert paths.product_master.exists()
    assert paths.review_chunks.exists()
    assert (paths.index_dir / "chroma" / "chroma.sqlite3").exists()
    assert not (paths.artifact_dir / "saas-demo-data.zip").exists()


def test_mixed_pricing_sources_are_reported() -> None:
    pricing = data_loader.canonicalize_pricing(
        pd.DataFrame(
            [
                {"product_name": "Example", "plan_name": "Kaggle", "plan_price_usd": 10},
                {
                    "product_name": "Example",
                    "plan_name": "Supplemental",
                    "monthly_price": 20,
                    "source_url": "https://example.com/pricing",
                    "source_accessed": "2026-05-02",
                },
            ]
        )
    )

    summary = data_loader._pricing_summary_frame(pricing)

    assert summary.loc[0, "pricing_source_type"] == "mixed"
    assert summary.loc[0, "pricing_source_urls"] == "https://example.com/pricing"
