import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, "chatbot/backend")
from app.llm_factory import create_chat_model


def test_groq_missing_key_does_not_fallback_to_openai(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "unused-openai-key")
    with pytest.raises(HTTPException) as exc_info:
        create_chat_model()
    assert exc_info.value.status_code == 503
    assert "GROQ_API_KEY" in exc_info.value.detail


def test_unknown_provider_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "unsupported")
    with pytest.raises(HTTPException) as exc_info:
        create_chat_model()
    assert "AI_PROVIDER" in exc_info.value.detail
