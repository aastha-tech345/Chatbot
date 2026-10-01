"""Provider selection for the Master Chatbot's application-agnostic planner."""

from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, status


def create_chat_model() -> Any:
    """Create the configured model without logging provider credentials."""
    provider = os.getenv("AI_PROVIDER", "").strip().lower()
    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Groq is selected but GROQ_API_KEY is not configured.")
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The Groq LangChain integration is unavailable.") from exc
        model = os.getenv("GROQ_MODEL", "").strip()
        if not model:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Groq is selected but GROQ_MODEL is not configured.")
        return ChatGroq(model=model, api_key=api_key, temperature=0)

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OpenAI is selected but OPENAI_API_KEY is not configured.")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The OpenAI LangChain integration is unavailable.") from exc
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        return ChatOpenAI(model=model, api_key=api_key, temperature=0)

    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI_PROVIDER must be configured as a supported provider.")
