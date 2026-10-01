"""Authentication-contract tests for the Master Chatbot SDK."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from master_chatbot import (
    AsyncMasterChatbotClient,
    MasterChatbotClient,
    MasterChatbotConfig,
    MasterChatbotConfigError,
)
from master_chatbot import http_client as http_client_module


class RecordingAsyncClient:
    """In-memory httpx replacement that records outgoing requests."""

    requests: list[dict[str, object]] = []

    def __init__(self, **_: object) -> None:
        pass

    async def __aenter__(self) -> "RecordingAsyncClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def post(self, url: str, **kwargs: object) -> httpx.Response:
        self.requests.append({"url": url, **kwargs})
        return httpx.Response(
            200,
            json={
                "success": True,
                "app_id": "his",
                "conversation_id": "conversation-1",
                "message": "ok",
                "session_id": "session-1",
                "request_id": "request-1",
                "intent": None,
                "data": [],
                "actions": [],
                "metadata": {},
            },
            request=httpx.Request("POST", url),
        )


def test_from_env_loads_sdk_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASTER_CHATBOT_URL", "https://chatbot.example.test/api/v1")
    monkeypatch.setenv("MASTER_CHATBOT_APP_ID", "his")
    monkeypatch.setenv("MASTER_CHATBOT_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("MASTER_CHATBOT_TIMEOUT", "12.5")
    monkeypatch.setenv("MASTER_CHATBOT_RETRIES", "4")

    config = MasterChatbotClient.from_env().config

    assert config.base_url == "https://chatbot.example.test/api/v1"
    assert config.app_id == "his"
    assert config.service_key == "test-service-key"
    assert config.timeout == 12.5
    assert config.retries == 4


def test_sync_chat_preserves_bearer_and_sends_service_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    RecordingAsyncClient.requests = []
    monkeypatch.setattr(http_client_module.httpx, "AsyncClient", RecordingAsyncClient)
    client = MasterChatbotClient(
        MasterChatbotConfig(
            base_url="https://chatbot.example.test/api/v1",
            app_id="his",
            service_key="test-service-key",
            retries=1,
        )
    )

    client.chat(
        message="Show my appointments",
        user_jwt_token="Bearer user-jwt",
        conversation_id="conversation-1",
        session_id="session-1",
        request_id="request-1",
    )

    assert len(RecordingAsyncClient.requests) == 1
    outgoing = RecordingAsyncClient.requests[0]
    headers = outgoing["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer user-jwt"
    assert headers["X-Master-Chatbot-Service-Key"] == "test-service-key"
    assert headers["X-Request-Id"] == "request-1"
    assert headers["X-Chat-Session-Id"] == "session-1"
    assert outgoing["url"] == "https://chatbot.example.test/api/v1/chat"
    body = outgoing["json"]
    assert isinstance(body, dict)
    assert body["conversation_id"] == "conversation-1"
    assert body["session_id"] == "session-1"
    assert body["request_id"] == "request-1"
    assert "user-jwt" not in str(body)


def test_missing_user_token_fails_before_http_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    def unexpected_client(**_: object) -> RecordingAsyncClient:
        calls.append(object())
        return RecordingAsyncClient()

    monkeypatch.setattr(http_client_module.httpx, "AsyncClient", unexpected_client)
    client = MasterChatbotClient(
        MasterChatbotConfig(
            base_url="https://chatbot.example.test",
            app_id="his",
            service_key="test-service-key",
            retries=1,
        )
    )

    with pytest.raises(ValueError, match="user_jwt_token"):
        asyncio.run(client.achat(message="Hello", user_jwt_token=""))

    assert calls == []


def test_async_chat_sends_normalized_bearer_and_service_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    RecordingAsyncClient.requests = []
    monkeypatch.setattr(http_client_module.httpx, "AsyncClient", RecordingAsyncClient)
    client = MasterChatbotClient(
        MasterChatbotConfig(
            base_url="https://chatbot.example.test",
            app_id="his",
            service_key="test-service-key",
            retries=1,
        )
    )

    asyncio.run(client.achat(message="Hello", user_jwt_token="user-jwt", request_id="request-2"))

    headers = RecordingAsyncClient.requests[0]["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer user-jwt"
    assert headers["X-Master-Chatbot-Service-Key"] == "test-service-key"
    assert RecordingAsyncClient.requests[0]["url"] == "https://chatbot.example.test/api/v1/chat"


def test_missing_service_key_fails_before_http_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASTER_CHATBOT_URL", "https://chatbot.example.test")
    monkeypatch.setenv("MASTER_CHATBOT_APP_ID", "his")
    monkeypatch.delenv("MASTER_CHATBOT_SERVICE_KEY", raising=False)
    calls: list[object] = []

    def unexpected_client(**_: object) -> RecordingAsyncClient:
        calls.append(object())
        return RecordingAsyncClient()

    monkeypatch.setattr(http_client_module.httpx, "AsyncClient", unexpected_client)

    with pytest.raises(MasterChatbotConfigError, match="MASTER_CHATBOT_SERVICE_KEY"):
        MasterChatbotClient.from_env()

    assert calls == []


def test_async_client_rejects_missing_service_key_before_transport() -> None:
    with pytest.raises(MasterChatbotConfigError, match="service_key"):
        AsyncMasterChatbotClient(
            MasterChatbotConfig(
                base_url="https://chatbot.example.test",
                app_id="his",
                service_key="",
            )
        )
