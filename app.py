from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

st.set_page_config(
    page_title="SaaSScout",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _sync_streamlit_secrets_to_env() -> None:
    keys = [
        "LLM_PROVIDER",
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "GROQ_BASE_URL",
        "DATA_ARTIFACT_URL",
        "USE_CHROMA",
        "PRODUCTION_MODE",
    ]
    try:
        for key in keys:
            if key in st.secrets and not os.getenv(key):
                os.environ[key] = str(st.secrets[key])
    except Exception:
        pass


_sync_streamlit_secrets_to_env()

from saas_copilot.data_loader import load_processed_or_demo  # noqa: E402
from saas_copilot.pipeline import (  # noqa: E402
    display_feature_name,
    list_available_features,
    list_categories,
    list_product_names,
    run_analysis,
)
from saas_copilot.llm import active_llm_available, active_llm_label  # noqa: E402
from saas_copilot.presets import DEMO_PRESETS  # noqa: E402


st.markdown(
    """
    <style>
    .block-container { padding-top: 1.25rem; max-width: 1440px; }
    [data-testid="stMetricValue"] { font-size: 1.25rem; }
    div[data-testid="stDataFrame"] { border: 1px solid #e7e9ee; border-radius: 8px; }
    .small-muted { color: #667085; font-size: 0.88rem; }
    .status-caption { color: #667085; font-size: 0.82rem; margin-top: -0.75rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

@st.cache_data(show_spinner=False)
def cached_categories() -> list[str]:
    return list_categories()


@st.cache_data(show_spinner=False)
def cached_product_names() -> list[str]:
    return list_product_names()


@st.cache_data(show_spinner=False)
def cached_features() -> list[str]:
    return list_available_features()


@st.cache_data(show_spinner=False, ttl=30)
def cached_llm_available(label: str) -> bool:
    return active_llm_available()


@st.cache_data(show_spinner=False)
def cached_demo_status(llm_label: str) -> dict[str, object]:
    products, reviews, notice = load_processed_or_demo()
    source = "Demo data" if "fictional demo data" in notice.lower() else "Kaggle/local data"
    chroma_status = "Unavailable"
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(ROOT / "data" / "indexes" / "chroma"))
        product_count = client.get_collection("products").count()
        review_count = client.get_collection("reviews").count()
        chroma_status = f"Ready ({product_count}/{review_count})"
    except Exception:
        pass

    return {
        "source": source,
        "product_count": len(products),
        "review_count": len(reviews),
        "category_count": products.get("category", pd.Series(dtype=str)).nunique(),
        "chroma_status": chroma_status,
        "llm_status": f"{llm_label} ready" if active_llm_available() else f"{llm_label} unavailable",
    }


def style_missing_data(frame: pd.DataFrame):
    if frame.empty:
        return frame
    marker_style = "background-color: #fff4d6; color: #7a4d00;"
    styles = pd.DataFrame("", index=frame.index, columns=frame.columns)
    for column in frame.columns:
        column_key = str(column).lower()
        for index, value in frame[column].items():
            text = str(value).strip().lower()
            is_missing_text = (
                pd.isna(value)
                or "pricing unavailable" in text
                or "structured feature evidence unavailable" in text
                or "no positive structured or review-derived feature flags" in text
                or "no rating" in text
                or "no review" in text
                or "no linked review" in text
            )
            is_zero_review_count = column_key in {"review count", "review_count"} and str(value) in {
                "0",
                "0.0",
            }
            if is_missing_text or is_zero_review_count:
                styles.loc[index, column] = marker_style
    return frame.style.apply(lambda _: styles, axis=None)


st.title("SaaSScout")

llm_label = active_llm_label()
try:
    status = cached_demo_status(llm_label)
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

status_cols = st.columns(5)
status_cols[0].metric("Data Source", str(status["source"]))
status_cols[1].metric("Products", int(status["product_count"]))
status_cols[2].metric("Reviews", int(status["review_count"]))
status_cols[3].metric("Chroma", str(status["chroma_status"]))
status_cols[4].metric("LLM", str(status["llm_status"]))

preset_labels = [preset["label"] for preset in DEMO_PRESETS]
selected_preset_label = st.selectbox("Demo preset", preset_labels, index=0)
preset = next(item for item in DEMO_PRESETS if item["label"] == selected_preset_label)
preset_key = selected_preset_label.lower().replace(" ", "_")
categories = cached_categories()
features = cached_features()
products = cached_product_names()

with st.sidebar:
    st.subheader("Filters")
    category_index = categories.index(preset["category"]) if preset["category"] in categories else 0
    category = st.selectbox("Category", categories, index=category_index, key=f"category_{preset_key}")

    apply_budget = st.checkbox(
        "Apply max monthly price",
        value=preset["max_price"] is not None,
        key=f"apply_budget_{preset_key}",
    )
    max_monthly_price = None
    if apply_budget:
        max_monthly_price = st.number_input(
            "Max monthly price",
            min_value=0.0,
            max_value=100000.0,
            value=float(preset["max_price"] or 50.0),
            step=5.0,
            key=f"max_price_{preset_key}",
        )

    default_features = [feature for feature in preset["features"] if feature in features]
    selected_features = st.multiselect(
        "Required features",
        features,
        default=default_features,
        key=f"features_{preset_key}",
        format_func=display_feature_name,
    )
    typed_features = st.text_input("Additional required features", value="", key=f"typed_features_{preset_key}")

    default_tools = [tool for tool in preset["tools"] if tool in products]
    compare_tools = st.multiselect(
        "Tools to compare", products, default=default_tools, key=f"tools_{preset_key}"
    )
    typed_tools = st.text_input("Additional tool names", value="", key=f"typed_tools_{preset_key}")

    top_k = st.slider(
        "Number of results",
        min_value=2,
        max_value=10,
        value=int(preset["top_k"]),
        key=f"top_k_{preset_key}",
    )
    model_available = cached_llm_available(llm_label)
    use_llm = st.checkbox(
        f"Use LLM rewrite ({llm_label})",
        value=model_available,
        help="Uses retrieved Chroma evidence as context. If the configured provider is unavailable, the app falls back to the grounded template.",
    )
    if not model_available:
        st.caption(f"LLM provider unavailable: {llm_label}. The grounded template remains available.")

query = st.text_area(
    "Analysis query",
    value=str(preset["query"]),
    height=110,
    key=f"query_{preset_key}",
)

left, right = st.columns([1, 4])
with left:
    run_clicked = st.button("Run Analysis", type="primary", use_container_width=True)
with right:
    st.markdown(
        '<div class="small-muted">Answers are limited to loaded structured data and retrieved review snippets.</div>',
        unsafe_allow_html=True,
    )

if run_clicked:
    required_features_text = ", ".join([*selected_features, typed_features]).strip(", ")
    compare_tools_text = ", ".join([*compare_tools, typed_tools]).strip(", ")

    with st.spinner("Retrieving products, scoring fit, and grounding the recommendation..."):
        result = run_analysis(
            query=query,
            category=category,
            max_monthly_price=max_monthly_price,
            required_features_text=required_features_text,
            compare_tools_text=compare_tools_text,
            top_k=top_k,
            use_llm=use_llm,
        )

    if "fictional demo data" in result.source_notice.lower():
        st.warning(result.source_notice)
    else:
        st.caption(result.source_notice)
    if result.llm_warning:
        st.warning(result.llm_warning)
    else:
        st.caption(f"LLM: {result.llm_provider} / {result.llm_model} ({result.llm_status})")

    metrics = st.columns(3)
    metrics[0].metric("Confidence", result.confidence.title())
    metrics[1].metric("Mapped Features", len(result.required_features))
    metrics[2].metric("Evidence Snippets", len(result.evidence_snippets))

    if result.evidence_snippets.empty:
        st.warning("No review snippets were retrieved for this answer. Treat it as structured-data-only guidance.")

    tab_answer, tab_comparison, tab_reviews, tab_evidence = st.tabs(["Answer", "Scorecard", "Reviews", "Evidence"])

    with tab_answer:
        st.markdown(result.answer)
        if result.ranking_explanation:
            st.subheader("Why This Ranking")
            for item in result.ranking_explanation:
                st.markdown(f"- {item}")
        if not result.recommended_tools.empty:
            st.subheader("Recommended Tools")
            st.dataframe(style_missing_data(result.recommended_tools), use_container_width=True, hide_index=True)

    with tab_comparison:
        if result.comparison_table.empty:
            st.info("No comparison rows available.")
        else:
            st.dataframe(style_missing_data(result.comparison_table), use_container_width=True, hide_index=True)

    with tab_reviews:
        if result.review_themes.empty:
            st.info("No review themes were retrieved.")
        else:
            st.dataframe(style_missing_data(result.review_themes), use_container_width=True, hide_index=True)

    with tab_evidence:
        if result.evidence_snippets.empty:
            st.info("No review evidence snippets were retrieved.")
        else:
            st.dataframe(style_missing_data(result.evidence_snippets), use_container_width=True, hide_index=True)

        st.subheader("Risks")
        for risk in result.risks:
            st.markdown(f"- {risk}")

        st.subheader("Suggested Follow-Up Questions")
        for question in result.follow_up_questions:
            st.markdown(f"- {question}")
else:
    st.caption("Set filters, enter a query, and run analysis.")
