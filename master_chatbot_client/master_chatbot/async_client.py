"""Dedicated async SDK facade for async web applications."""

from __future__ import annotations

from master_chatbot.config import MasterChatbotConfig
from master_chatbot.exceptions import MasterChatbotConfigError
from master_chatbot.http_client import MasterChatbotHTTPClient
from master_chatbot.models import ChatRequest, ChatResponse
from master_chatbot.utils import build_headers, new_request_id


class AsyncMasterChatbotClient:
    """Asynchronous Master Chatbot client using the documented HTTP contract."""

    def __init__(self, config: MasterChatbotConfig):
        try:
            config.validate()
        except ValueError as exc:
            raise MasterChatbotConfigError(str(exc)) from exc
        self.config = config
        self._transport = MasterChatbotHTTPClient(config)

    @classmethod
    def from_env(cls) -> "AsyncMasterChatbotClient":
        try:
            return cls(MasterChatbotConfig.from_env())
        except ValueError as exc:
            raise MasterChatbotConfigError(str(exc)) from exc

    async def chat(
        self,
        *,
        message: str,
        user_jwt_token: str,
        conversation_id: str | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
    ) -> ChatResponse:
        resolved_request_id = new_request_id(request_id)
        request = ChatRequest(
            app_id=self.config.app_id,
            message=message,
            conversation_id=conversation_id,
            session_id=session_id,
            request_id=resolved_request_id,
        )
        headers = build_headers(
            user_jwt_token=user_jwt_token,
            service_key=self.config.service_key,
            request_id=resolved_request_id,
            session_id=session_id,
        )
        return await self._transport.post_chat(
            request=request,
            headers=headers,
        )

    achat = chat
