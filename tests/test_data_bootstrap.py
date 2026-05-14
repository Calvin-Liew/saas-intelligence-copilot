from __future__ import annotations

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
