"""
AIConfigManager — DB-backed runtime AI configuration.

The database is the SINGLE SOURCE OF TRUTH for AI provider and credentials.
.env variables (AI_PROVIDER, GROQ_API_KEY, GROQ_MODEL) are no longer used
for runtime LLM creation after migration. They may still exist in .env for
backward compatibility but are NOT read here at runtime.

Flow:
  DB (ai_credentials WHERE is_active=True)
      ↓ decrypt API key
  AIConfigManager.get_active()
      ↓
  AIProviderFactory / llm_factory
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


@dataclass
class AIRuntimeConfig:
    """Decrypted runtime AI configuration — never serialized or logged."""
    provider_key: str       # e.g. "groq", "openai"
    api_key: str            # plaintext — used only for LLM construction
    model: str
    temperature: float | None
    max_tokens: int | None
    top_p: float | None
    credential_id: str
    provider_id: str

    @property
    def api_key_masked(self) -> str:
        if not self.api_key:
            return ""
        suffix = self.api_key[-4:] if len(self.api_key) >= 4 else self.api_key
        return f"************{suffix}"


class AIConfigManager:
    """
    Thread-safe in-process cache for the active AI credential.

    Loads from DB on first use and after any invalidation.
    Never reads AI_PROVIDER / GROQ_API_KEY / GROQ_MODEL from the environment.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: AIRuntimeConfig | None = None

    # ── Public API ────────────────────────────────────────────────────────

    async def get_active(self) -> AIRuntimeConfig:
        """Return the active AI configuration from the DB cache."""
        with self._lock:
            if self._cache is not None:
                return self._cache
        # Load outside the lock to avoid blocking
        config = await self._load_from_db()
        with self._lock:
            self._cache = config
        return config

    def invalidate(self) -> None:
        """Invalidate the cache — next call to get_active() reloads from DB."""
        with self._lock:
            self._cache = None
        logger.info("[AI_CONFIG] cache invalidated")

    def update(self, *, ai_provider: str, groq_api_key: str, groq_model: str) -> Any:
        """
        Legacy compatibility shim called by AIService._sync_to_manager().
        Invalidates the cache so the next request reloads from DB.
        The DB is already updated before this is called.
        """
        self.invalidate()
        # Return a minimal public dict for callers that expect it
        return _LegacyConfigProxy(ai_provider=ai_provider, groq_model=groq_model)

    # ── Internal ─────────────────────────────────────────────────────────

    async def _load_from_db(self) -> AIRuntimeConfig:
        """Load the active AI credential from DB and decrypt the API key."""
        try:
            from .database import AsyncSessionLocal
            from .repositories import AICredentialRepo, AIProviderRepo
            from .crypto import decrypt

            async with AsyncSessionLocal() as db:
                cred_repo = AICredentialRepo(db)
                provider_repo = AIProviderRepo(db)

                cred = await cred_repo.get_active()
                if cred is None:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="AI_CONFIGURATION_NOT_FOUND: No active AI configuration found. "
                               "Please activate an AI configuration in the Admin panel.",
                    )

                provider = await provider_repo.get_by_id(cred.provider_id)
                if provider is None or not provider.is_enabled:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="AI_PROVIDER_NOT_FOUND: The AI provider for the active configuration "
                               "is not found or disabled.",
                    )

                try:
                    raw_key = decrypt(cred.api_key_encrypted) if cred.api_key_encrypted else ""
                except Exception as exc:
                    logger.error("[AI_CONFIG] failed to decrypt API key credential_id=%s error=%s", cred.id, exc)
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="AI_CONFIGURATION_INVALID: Failed to decrypt the AI API key.",
                    ) from exc

                if not raw_key:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="AI_CONFIGURATION_INVALID: The active AI credential has no API key.",
                    )

                config = AIRuntimeConfig(
                    provider_key=provider.provider_key,
                    api_key=raw_key,
                    model=cred.model,
                    temperature=float(cred.temperature) if cred.temperature is not None else None,
                    max_tokens=cred.max_tokens,
                    top_p=float(cred.top_p) if cred.top_p is not None else None,
                    credential_id=cred.id,
                    provider_id=cred.provider_id,
                )
                logger.info(
                    "[AI_CONFIG] loaded provider=%s model=%s credential_id=%s",
                    config.provider_key,
                    config.model,
                    config.credential_id,
                )
                return config

        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("[AI_CONFIG] unexpected error loading from DB: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"AI_CONFIGURATION_NOT_FOUND: Could not load AI configuration: {type(exc).__name__}",
            ) from exc


class _LegacyConfigProxy:
    """Minimal object returned by update() for backward-compatible callers."""
    def __init__(self, *, ai_provider: str, groq_model: str) -> None:
        self.ai_provider = ai_provider
        self.groq_model = groq_model

    def public_dict(self) -> dict:
        return {"ai_provider": self.ai_provider, "groq_model": self.groq_model}


# Module-level singleton
ai_config_manager = AIConfigManager()
