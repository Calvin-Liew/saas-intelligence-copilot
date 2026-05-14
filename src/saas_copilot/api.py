from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import asynccontextmanager
from copy import deepcopy
from time import monotonic
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import PATHS, RUNTIME
from .data_loader import load_processed_or_demo
from .enrichment import factgrid_match_count, load_open_source_alternatives, wikidata_match_count
from .llm import active_llm_available, active_llm_label
from .pipeline import (
    display_feature_name,
    run_analysis,
)
from .presets import DEMO_PRESETS
from .scoring import feature_columns, is_review_derived_feature

_CHROMA_STATUS_CACHE: tuple[float, dict[str, Any]] | None = None
_CHROMA_SUCCESS_TTL_SECONDS = 300
_CHROMA_FAILURE_TTL_SECONDS = 10
_STATUS_CACHE: tuple[float, dict[str, Any]] | None = None
_STATUS_TTL_SECONDS = 60
_OPTIONS_CACHE: tuple[float, dict[str, Any]] | None = None
_OPTIONS_TTL_SECONDS = 300
_WARMUP_RETRY_AFTER_SECONDS = 3
_WARMUP_LOCK = threading.Lock()
_WARMUP_THREAD: threading.Thread | None = None
_WARMUP_STATE = {
    "state": "idle",
    "message": "Backend warmup has not started.",
    "error": "",
}


class AnalyzeRequest(BaseModel):
    query: str
    category: str | None = "All"
    max_monthly_price: float | None = None
    required_features: list[str] = Field(default_factory=list)
    additional_required_features: str = ""
    compare_tools: list[str] = Field(default_factory=list)
    additional_tool_names: str = ""
    top_k: int = Field(default=5, ge=1, le=20)
    use_llm: bool = True


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _start_warmup()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="SaaSScout API", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_frontend_origins(),
        allow_origin_regex=_frontend_origin_regex(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/bootstrap")
    def bootstrap() -> dict[str, Any]:
        return _bootstrap_payload()

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        _require_warmup_ready()
        return _status_payload()

    @app.get("/api/options")
    def options() -> dict[str, Any]:
        _require_warmup_ready()
        return _options_payload()

    @app.post("/api/analyze")
    def analyze(payload: AnalyzeRequest) -> dict[str, Any]:
        _require_warmup_ready()
        required_features_text = ", ".join(
            [*payload.required_features, payload.additional_required_features]
        ).strip(", ")
        compare_tools_text = ", ".join(
            [*payload.compare_tools, payload.additional_tool_names]
        ).strip(", ")
        result = run_analysis(
            query=payload.query,
            category=payload.category,
            max_monthly_price=payload.max_monthly_price,
            required_features_text=required_features_text,
            compare_tools_text=compare_tools_text,
            top_k=payload.top_k,
            use_llm=payload.use_llm,
        )
        return {
            "answer": result.answer,
            "confidence": result.confidence,
            "source_notice": result.source_notice,
            "llm": {
                "provider": result.llm_provider,
                "model": result.llm_model,
                "status": result.llm_status,
                "warning": result.llm_warning,
            },
            "required_features": result.required_features,
            "recommended_tools": _records(result.recommended_tools),
            "comparison_table": _records(result.comparison_table),
            "review_themes": _records(result.review_themes),
            "evidence_snippets": _records(result.evidence_snippets),
            "enterprise_metadata": _records(result.enterprise_metadata),
            "vendor_metadata": _records(result.vendor_metadata),
            "open_source_alternatives": _records(result.open_source_alternatives),
            "ranking_explanation": result.ranking_explanation,
            "risks": result.risks,
            "follow_up_questions": result.follow_up_questions,
        }

    return app


def _start_warmup() -> None:
    global _WARMUP_THREAD
    with _WARMUP_LOCK:
        thread_alive = _WARMUP_THREAD is not None and _WARMUP_THREAD.is_alive()
        if _WARMUP_STATE["state"] == "ready":
            return
        if _WARMUP_STATE["state"] == "warming":
            if not thread_alive:
                _set_warmup_state_locked(
                    "error",
                    "Backend warmup stopped before completing.",
                    "Warmup thread stopped before completing.",
                )
            else:
                return

        _set_warmup_state_locked(
            "warming",
            "Preparing product data, Chroma indexes, enrichment metadata, and options.",
        )
        _WARMUP_THREAD = threading.Thread(
            target=_warmup_worker,
            name="saasscout-warmup",
            daemon=True,
        )
        _WARMUP_THREAD.start()


def _warmup_worker() -> None:
    try:
        _status_payload()
        _options_payload()
    except Exception as exc:
        _set_warmup_state(
            "error",
            f"Backend warmup failed: {type(exc).__name__}.",
            str(exc),
        )
        return
    _set_warmup_state(
        "ready",
        "Product data, Chroma indexes, enrichment metadata, and options are ready.",
    )


def _bootstrap_payload() -> dict[str, Any]:
    snapshot = _warmup_snapshot()
    if snapshot["state"] in {"idle", "error"}:
        _start_warmup()
        snapshot = _warmup_snapshot()
    return {
        "ready": snapshot["state"] == "ready",
        "warming": snapshot["state"] == "warming",
        "error": snapshot["error"] if snapshot["state"] == "error" else "",
        "message": snapshot["message"],
    }


def _require_warmup_ready() -> None:
    snapshot = _warmup_snapshot()
    if snapshot["state"] in {"idle", "error"}:
        _start_warmup()
        snapshot = _warmup_snapshot()
    if snapshot["state"] == "ready":
        return
    raise HTTPException(
        status_code=503,
        detail=snapshot["message"],
        headers={"Retry-After": str(_WARMUP_RETRY_AFTER_SECONDS)},
    )


def _warmup_snapshot() -> dict[str, str]:
    with _WARMUP_LOCK:
        return dict(_WARMUP_STATE)


def _set_warmup_state(state: str, message: str, error: str = "") -> None:
    with _WARMUP_LOCK:
        _set_warmup_state_locked(state, message, error)


def _set_warmup_state_locked(state: str, message: str, error: str = "") -> None:
    _WARMUP_STATE["state"] = state
    _WARMUP_STATE["message"] = message
    _WARMUP_STATE["error"] = error


def _status_payload() -> dict[str, Any]:
    global _STATUS_CACHE
    now = monotonic()
    if _STATUS_CACHE and _STATUS_CACHE[0] > now:
        return deepcopy(_STATUS_CACHE[1])

    products, reviews, notice = load_processed_or_demo()
    chroma = _chroma_status()
    enrichment = _enrichment_status(products)
    llm_available = active_llm_available()
    source = "Demo data" if "fictional demo data" in notice.lower() else "Kaggle/local data"
    payload = {
        "source": source,
        "source_notice": notice,
        "product_count": len(products),
        "review_count": len(reviews),
        "category_count": int(products.get("category", pd.Series(dtype=str)).nunique()),
        "chroma": chroma,
        "enrichment": enrichment,
        "llm": {
            "label": active_llm_label(),
            "available": llm_available,
            "provider": RUNTIME.llm_provider,
            "model": _active_model(),
            "status": "ok" if llm_available else "unavailable",
            "warning": "" if llm_available else "Configured LLM is unavailable; analyze requests will use the grounded template fallback.",
        },
    }
    _STATUS_CACHE = (now + _STATUS_TTL_SECONDS, payload)
    return deepcopy(payload)


def _options_payload() -> dict[str, Any]:
    global _OPTIONS_CACHE
    now = monotonic()
    if _OPTIONS_CACHE and _OPTIONS_CACHE[0] > now:
        return deepcopy(_OPTIONS_CACHE[1])

    products, _, _ = load_processed_or_demo()
    features = feature_columns(products)
    payload = {
        "categories": _categories_from_products(products),
        "products": _product_names_from_products(products),
        "features": [
            {
                "id": feature,
                "label": display_feature_name(feature),
                "review_derived": is_review_derived_feature(feature),
            }
            for feature in features
        ],
        "demo_presets": DEMO_PRESETS,
    }
    _OPTIONS_CACHE = (now + _OPTIONS_TTL_SECONDS, payload)
    return deepcopy(payload)


def _frontend_origins() -> list[str]:
    raw = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _frontend_origin_regex() -> str | None:
    raw = os.getenv(
        "FRONTEND_ORIGIN_REGEX",
        r"https://([a-z0-9-]+--)?saas-intelligence-copilot-calvi\.netlify\.app",
    ).strip()
    return raw or None


def _active_model() -> str:
    if RUNTIME.llm_provider == "groq":
        return RUNTIME.groq_model
    if RUNTIME.llm_provider == "ollama":
        return RUNTIME.ollama_model
    return "grounded-template"


def _chroma_status() -> dict[str, Any]:
    global _CHROMA_STATUS_CACHE
    now = monotonic()
    if _CHROMA_STATUS_CACHE and _CHROMA_STATUS_CACHE[0] > now:
        return dict(_CHROMA_STATUS_CACHE[1])

    status = _compute_chroma_status()
    ttl = _CHROMA_SUCCESS_TTL_SECONDS if status["ready"] else _CHROMA_FAILURE_TTL_SECONDS
    _CHROMA_STATUS_CACHE = (now + ttl, status)
    return dict(status)


def _compute_chroma_status() -> dict[str, Any]:
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(PATHS.index_dir / "chroma"))
        product_count = client.get_collection("products").count()
        review_count = client.get_collection("reviews").count()
        alternatives_count = _optional_collection_count(client, "open_source_alternatives")
        return {
            "ready": product_count > 0 and review_count > 0,
            "product_count": product_count,
            "review_count": review_count,
            "alternatives_count": alternatives_count,
            "status": f"Ready ({product_count}/{review_count})",
        }
    except Exception as exc:
        return _chroma_sqlite_status(exc)


def _optional_collection_count(client, name: str) -> int:
    try:
        return int(client.get_collection(name).count())
    except Exception:
        return 0


def _chroma_sqlite_status(source_error: Exception) -> dict[str, Any]:
    db_path = PATHS.index_dir / "chroma" / "chroma.sqlite3"
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                """
                select c.name, count(e.id)
                from collections c
                join segments s on s.collection = c.id and s.scope = 'METADATA'
                left join embeddings e on e.segment_id = s.id
                where c.name in ('products', 'reviews', 'open_source_alternatives')
                group by c.name
                """
            ).fetchall()
        counts = {str(name): int(count) for name, count in rows}
        product_count = counts.get("products", 0)
        review_count = counts.get("reviews", 0)
        alternatives_count = counts.get("open_source_alternatives", 0)
        if product_count > 0 and review_count > 0:
            return {
                "ready": True,
                "product_count": product_count,
                "review_count": review_count,
                "alternatives_count": alternatives_count,
                "status": f"Ready ({product_count}/{review_count})",
            }
    except Exception:
        pass

    return {
        "ready": False,
        "product_count": 0,
        "review_count": 0,
        "alternatives_count": 0,
        "status": f"Unavailable ({type(source_error).__name__})",
    }


def _enrichment_status(products: pd.DataFrame) -> dict[str, Any]:
    try:
        alternatives_count = len(load_open_source_alternatives())
    except Exception:
        alternatives_count = 0
    matched_factgrid = factgrid_match_count(products)
    matched_wikidata = wikidata_match_count(products)
    ready = matched_factgrid > 0 or matched_wikidata > 0 or alternatives_count > 0
    return {
        "ready": ready,
        "factgrid_matches": matched_factgrid,
        "wikidata_matches": matched_wikidata,
        "open_source_alternatives": alternatives_count,
        "status": (
            f"Ready (FactGrid {matched_factgrid} / Wikidata {matched_wikidata} / OSS {alternatives_count})"
            if ready
            else "Missing"
        ),
    }


def _categories_from_products(products: pd.DataFrame) -> list[str]:
    categories = sorted(
        [item for item in products.get("category", pd.Series(dtype=str)).dropna().unique() if str(item)]
    )
    return ["All", *categories]


def _product_names_from_products(products: pd.DataFrame) -> list[str]:
    return sorted(products.get("product_name", pd.Series(dtype=str)).dropna().astype(str).unique())


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    clean = frame.astype(object).where(pd.notna(frame), None)
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in clean.to_dict("records")
    ]


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


app = create_app()
