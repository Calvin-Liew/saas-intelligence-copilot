from __future__ import annotations

from dataclasses import dataclass

import requests

from .config import RUNTIME
from .prompts import SYSTEM_PROMPT


@dataclass(frozen=True)
class LLMResult:
    content: str | None
    provider: str
    model: str
    status: str
    warning: str = ""


def default_ollama_model() -> str:
    return RUNTIME.ollama_model


def default_online_model() -> str:
    return RUNTIME.groq_model


def active_llm_label() -> str:
    provider = RUNTIME.llm_provider
    if provider == "groq":
        return f"Groq {RUNTIME.groq_model}"
    if provider == "ollama":
        return f"Ollama {RUNTIME.ollama_model}"
    return "Template fallback"


def active_llm_available() -> bool:
    if RUNTIME.llm_provider == "groq":
        return groq_available()
    if RUNTIME.llm_provider == "ollama":
        return ollama_available()
    return True


def ollama_available(model: str | None = None) -> bool:
    model = model or RUNTIME.ollama_model
    if not model:
        return False
    try:
        response = requests.get(f"{RUNTIME.ollama_base_url.rstrip('/')}/api/tags", timeout=3)
        response.raise_for_status()
        models = response.json().get("models", [])
    except Exception:
        return False
    return any(item.get("name") == model for item in models)


def groq_available() -> bool:
    return bool(RUNTIME.groq_api_key)


def generate_answer(
    query: str,
    context: str,
    grounded_draft: str,
) -> LLMResult:
    provider = RUNTIME.llm_provider
    if provider == "template":
        return LLMResult(
            content=None,
            provider="template",
            model="grounded-template",
            status="fallback",
            warning="Template mode is enabled.",
        )
    if provider == "groq":
        result = generate_with_groq(query=query, context=context, grounded_draft=grounded_draft)
        if result.content:
            return result
        return LLMResult(
            content=None,
            provider="template",
            model="grounded-template",
            status="fallback",
            warning=result.warning or "Groq generation failed; using grounded template.",
        )

    result = generate_with_ollama_result(query=query, context=context, grounded_draft=grounded_draft)
    if result.content:
        return result
    return LLMResult(
        content=None,
        provider="template",
        model="grounded-template",
        status="fallback",
        warning=result.warning or "Ollama generation failed; using grounded template.",
    )


def generate_with_groq(
    query: str,
    context: str,
    model: str | None = None,
    grounded_draft: str | None = None,
) -> LLMResult:
    model = model or RUNTIME.groq_model
    if not RUNTIME.groq_api_key:
        return LLMResult(
            content=None,
            provider="groq",
            model=model,
            status="unavailable",
            warning="GROQ_API_KEY is not configured; using grounded template.",
        )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(query, context, grounded_draft)},
        ],
        "temperature": 0,
        "top_p": 0.2,
        "max_tokens": 900,
    }
    try:
        response = requests.post(
            f"{RUNTIME.groq_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {RUNTIME.groq_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        if response.status_code == 429:
            return LLMResult(
                content=None,
                provider="groq",
                model=model,
                status="rate_limited",
                warning="Groq rate limit reached; using grounded template.",
            )
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        return LLMResult(content=_strip_thinking(content), provider="groq", model=model, status="ok")
    except Exception as exc:
        return LLMResult(
            content=None,
            provider="groq",
            model=model,
            status="error",
            warning=f"Groq generation failed ({type(exc).__name__}); using grounded template.",
        )


def generate_with_ollama_result(
    query: str,
    context: str,
    model: str | None = None,
    grounded_draft: str | None = None,
) -> LLMResult:
    model = model or RUNTIME.ollama_model
    content = generate_with_ollama(query, context, model=model, grounded_draft=grounded_draft)
    if content:
        return LLMResult(content=_strip_thinking(content), provider="ollama", model=model, status="ok")
    return LLMResult(
        content=None,
        provider="ollama",
        model=model,
        status="unavailable",
        warning="Ollama generation failed; using grounded template.",
    )


def generate_with_ollama(
    query: str,
    context: str,
    model: str | None = None,
    grounded_draft: str | None = None,
) -> str | None:
    model = model or RUNTIME.ollama_model
    if not model:
        return None

    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _user_prompt(query, context, grounded_draft),
            },
        ],
        "options": {
            "temperature": 0,
            "top_p": 0.2,
            "num_predict": 900,
        },
    }
    try:
        response = requests.post(
            f"{RUNTIME.ollama_base_url.rstrip('/')}/api/chat", json=payload, timeout=60
        )
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content")
    except Exception:
        return None


def _user_prompt(query: str, context: str, grounded_draft: str | None) -> str:
    if grounded_draft:
        return f"""User query:
{query}

Retrieved evidence:
{context}

Grounded draft answer:
{grounded_draft}

Formatting requirements:
- Rewrite the grounded draft into a concise procurement-style answer.
- Use only facts present in the grounded draft or retrieved evidence.
- Do not add vendor features, prices, pricing tiers, market reputation, or product claims from outside the evidence.
- Preserve all missing-data caveats.
- Do not include hidden reasoning, chain-of-thought, or <think> tags.
- End after the verification questions. Do not include a task or instruction section.
"""

    return f"User query:\n{query}\n\nRetrieved evidence:\n{context}"


def _strip_thinking(content: str | None) -> str | None:
    if not content:
        return content
    text = str(content)
    while text.lstrip().lower().startswith("<think>"):
        start = text.lower().find("<think>")
        end = text.lower().find("</think>", start)
        if end == -1:
            break
        text = text[:start] + text[end + len("</think>") :]
    return text.strip()
