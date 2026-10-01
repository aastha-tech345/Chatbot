"""Public synchronous and compatibility-async Master Chatbot client."""

from __future__ import annotations

import asyncio

import httpx

from master_chatbot.async_client import AsyncMasterChatbotClient
from master_chatbot.config import MasterChatbotConfig
from master_chatbot.exceptions import MasterChatbotConfigError
from master_chatbot.http_client import raise_for_response
from master_chatbot.models import ChatResponse
from master_chatbot.utils import build_headers, normalize_bearer_token


class MasterChatbotClient:
    """HTTP client for the Master Chatbot service.

    ``chat`` is for synchronous applications. ``achat`` remains available for
    FastAPI and other asynchronous integrations for backward compatibility.
    """

    def __init__(self, config: MasterChatbotConfig | None = None):
        try:
            self.config = config or MasterChatbotConfig.from_env()
        except ValueError as exc:
            raise MasterChatbotConfigError(str(exc)) from exc
        try:
            self.config.validate()
        except ValueError as exc:
            raise MasterChatbotConfigError(str(exc)) from exc
        self._async_client = AsyncMasterChatbotClient(self.config)

    @classmethod
    def from_env(cls) -> "MasterChatbotClient":
        return cls()

    def _build_headers(
        self,
        user_jwt_token: str,
        request_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, str]:
        """Compatibility helper used by integrations and unit tests."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": normalize_bearer_token(user_jwt_token),
            "X-Master-Chatbot-Service-Key": self.config.service_key,
        }
        if request_id is None:
            return headers
        headers.update(
            build_headers(
                user_jwt_token=user_jwt_token,
                service_key=self.config.service_key,
                request_id=request_id,
                session_id=session_id,
            )
        )
        return headers

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Compatibility wrapper for documented error mapping."""
        raise_for_response(response)

    def chat(
        self,
        message: str,
        user_jwt_token: str,
        conversation_id: str | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> ChatResponse:
        """Send a synchronous chat request.

        Use :meth:`achat` inside an active event loop.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.achat(
                    message=message,
                    user_jwt_token=user_jwt_token,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    request_id=request_id,
                )
            )
        raise RuntimeError("chat() cannot run inside an event loop; use await achat() instead")

    async def achat(
        self,
        message: str,
        user_jwt_token: str,
        conversation_id: str | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> ChatResponse:
        """Send an asynchronous chat request."""
        return await self._async_client.chat(
            message=message,
            user_jwt_token=user_jwt_token,
            conversation_id=conversation_id,
            session_id=session_id,
            request_id=request_id,
        )
