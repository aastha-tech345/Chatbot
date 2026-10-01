"""
AIProviderFactory — builds LLM clients from DB-backed configuration.

Flow:
  AIConfigManager.get_active()
      ↓ (decrypted API key, provider_key, model, params)
  create_chat_model()
      ↓
  ChatGroq / ChatOpenAI / etc.

NEVER reads AI_PROVIDER / GROQ_API_KEY / GROQ_MODEL from environment at runtime.
Those env vars may still exist in .env for legacy/migration purposes only.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status

from .ai_config import ai_config_manager, AIRuntimeConfig

logger = logging.getLogger(__name__)


def _build_groq(config: AIRuntimeConfig) -> Any:
    if not config.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI_CONFIGURATION_INVALID: Groq provider selected but API key is not configured.",
        )
    if not config.model:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI_CONFIGURATION_INVALID: Groq provider selected but model is not configured.",
        )
    try:
        from langchain_groq import ChatGroq
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The Groq LangChain integration is unavailable.",
        ) from exc

    kwargs: dict[str, Any] = {"model": config.model, "api_key": config.api_key, "temperature": 0}
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature
    return ChatGroq(**kwargs)


def _build_openai(config: AIRuntimeConfig) -> Any:
    if not config.api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI_CONFIGURATION_INVALID: OpenAI provider selected but API key is not configured.",
        )
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The OpenAI LangChain integration is unavailable.",
        ) from exc

    model = config.model or "gpt-4o-mini"
    kwargs: dict[str, Any] = {"model": model, "api_key": config.api_key, "temperature": 0}
    if config.temperature is not None:
        kwargs["temperature"] = config.temperature
    return ChatOpenAI(**kwargs)


_BUILDERS = {
    "groq": _build_groq,
    "openai": _build_openai,
}


async def create_chat_model() -> Any:
    """
    Create and return an LLM client using the active DB configuration.

    This is the ONLY place LLM clients are constructed.
    Raises HTTP 503 with a clear error code if no configuration is active.
    """
    config = await ai_config_manager.get_active()

    builder = _BUILDERS.get(config.provider_key)
    if builder is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI_PROVIDER_NOT_SUPPORTED: Provider '{config.provider_key}' is not supported. "
                   f"Supported providers: {', '.join(_BUILDERS)}",
        )

    logger.debug(
        "[LLM_FACTORY] building provider=%s model=%s credential_id=%s",
        config.provider_key,
        config.model,
        config.credential_id,
    )
    return builder(config)
