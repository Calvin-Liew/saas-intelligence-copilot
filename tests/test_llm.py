from __future__ import annotations

from types import SimpleNamespace

import requests

from saas_copilot import llm


class _FailingResponse:
    status_code = 500

    def raise_for_status(self) -> None:
        raise requests.HTTPError("server error")


def test_groq_generation_falls_back_with_visible_warning(monkeypatch) -> None:
    monkeypatch.setattr(
        llm,
        "RUNTIME",
        SimpleNamespace(
            llm_provider="groq",
            groq_api_key="test-key",
            groq_model="qwen/qwen3-32b",
            groq_base_url="https://api.groq.com/openai/v1",
            ollama_model="qwen2.5:1.5b",
            ollama_base_url="http://localhost:11434",
        ),
    )
    monkeypatch.setattr(llm.requests, "post", lambda *args, **kwargs: _FailingResponse())

    result = llm.generate_answer(
        query="Compare tools",
        context="Retrieved evidence",
        grounded_draft="Direct answer: pricing unavailable.",
    )

    assert result.provider == "template"
    assert result.status == "fallback"
    assert result.content is None
    assert "Groq generation failed" in result.warning


def test_thinking_tags_are_removed_from_llm_output() -> None:
    assert llm._strip_thinking("<think>private reasoning</think>\n\nDirect answer.") == "Direct answer."
