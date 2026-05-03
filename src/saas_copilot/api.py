from __future__ import annotations

import os
from typing import Any

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import PATHS, RUNTIME
from .data_loader import load_processed_or_demo
from .llm import active_llm_available, active_llm_label
from .pipeline import (
    display_feature_name,
    list_available_features,
    list_categories,
    list_product_names,
    run_analysis,
)
from .presets import DEMO_PRESETS
from .scoring import is_review_derived_feature


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


def create_app() -> FastAPI:
    app = FastAPI(title="SaaS Intelligence Copilot API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_frontend_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        products, reviews, notice = load_processed_or_demo()
        chroma = _chroma_status()
        llm_available = active_llm_available()
        source = "Demo data" if "fictional demo data" in notice.lower() else "Kaggle/local data"
        return {
            "source": source,
            "source_notice": notice,
            "product_count": len(products),
            "review_count": len(reviews),
            "category_count": int(products.get("category", pd.Series(dtype=str)).nunique()),
            "chroma": chroma,
            "llm": {
                "label": active_llm_label(),
                "available": llm_available,
                "provider": RUNTIME.llm_provider,
                "model": _active_model(),
                "status": "ok" if llm_available else "unavailable",
                "warning": "" if llm_available else "Configured LLM is unavailable; analyze requests will use the grounded template fallback.",
            },
        }

    @app.get("/api/options")
    def options() -> dict[str, Any]:
        features = list_available_features()
        return {
            "categories": list_categories(),
            "products": list_product_names(),
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

    @app.post("/api/analyze")
    def analyze(payload: AnalyzeRequest) -> dict[str, Any]:
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
            "ranking_explanation": result.ranking_explanation,
            "risks": result.risks,
            "follow_up_questions": result.follow_up_questions,
        }

    return app


def _frontend_origins() -> list[str]:
    raw = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _active_model() -> str:
    if RUNTIME.llm_provider == "groq":
        return RUNTIME.groq_model
    if RUNTIME.llm_provider == "ollama":
        return RUNTIME.ollama_model
    return "grounded-template"


def _chroma_status() -> dict[str, Any]:
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(PATHS.index_dir / "chroma"))
        product_count = client.get_collection("products").count()
        review_count = client.get_collection("reviews").count()
        return {
            "ready": product_count > 0 and review_count > 0,
            "product_count": product_count,
            "review_count": review_count,
            "status": f"Ready ({product_count}/{review_count})",
        }
    except Exception as exc:
        return {
            "ready": False,
            "product_count": 0,
            "review_count": 0,
            "status": f"Unavailable ({type(exc).__name__})",
        }


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
