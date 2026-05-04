from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class DataPaths:
    raw_dir: Path = PROJECT_ROOT / "data" / "raw"
    processed_dir: Path = PROJECT_ROOT / "data" / "processed"
    index_dir: Path = PROJECT_ROOT / "data" / "indexes"
    artifact_dir: Path = PROJECT_ROOT / "data" / "artifacts"
    supplemental_dir: Path = PROJECT_ROOT / "data" / "supplemental"
    product_master: Path = PROJECT_ROOT / "data" / "processed" / "product_master.csv"
    review_chunks: Path = PROJECT_ROOT / "data" / "processed" / "review_chunks.csv"
    unmatched_records: Path = PROJECT_ROOT / "data" / "processed" / "unmatched_records.csv"
    supplemental_pricing: Path = PROJECT_ROOT / "data" / "supplemental" / "support_tool_pricing.csv"
    factgrid_enrichment: Path = PROJECT_ROOT / "data" / "processed" / "factgrid_enrichment.csv"
    wikidata_vendor_facts: Path = PROJECT_ROOT / "data" / "processed" / "wikidata_vendor_facts.csv"
    open_source_alternatives: Path = PROJECT_ROOT / "data" / "processed" / "open_source_alternatives.csv"
    enrichment_qa: Path = PROJECT_ROOT / "data" / "processed" / "enrichment_qa.csv"


@dataclass(frozen=True)
class RuntimeConfig:
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama").lower()
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    groq_model: str = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")
    data_artifact_url: str = os.getenv("DATA_ARTIFACT_URL", "")
    production_mode: bool = os.getenv("PRODUCTION_MODE", "0").lower() in {"1", "true", "yes"}
    use_chroma: bool = os.getenv("USE_CHROMA", "1").lower() not in {"0", "false", "no"}


PATHS = DataPaths()
RUNTIME = RuntimeConfig()
