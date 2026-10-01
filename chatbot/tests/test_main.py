import asyncio
import base64
import hashlib
import hmac
import json
import sys
import time

import httpx
import pytest
from fastapi import HTTPException

sys.path.insert(0, "chatbot/backend")

from app.main import (
    ApplicationRegistrationRequest,
    RouteSyncRequest,
    _require_registration_key,
    app,
    register_application,
    sync_application_routes,
    unregister_application,
)
from app.app_registry import ApplicationRegistry


def _hs256_token(secret: str) -> str:
    def encode(value: dict[str, object]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = encode({"alg": "HS256", "typ": "JWT"})
    claims = encode({"sub": "user-1", "exp": int(time.time()) + 60})
    signature = hmac.new(secret.encode(), f"{header}.{claims}".encode(), hashlib.sha256).digest()
    return f"{header}.{claims}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def _configure_his_auth(monkeypatch) -> tuple[str, dict[str, str]]:  # noqa: ANN001
    secret = "test-his-jwt-secret"
    monkeypatch.setenv("HIS_API_URL", "http://example.test")
    monkeypatch.setenv("HIS_JWT_SECRET", secret)
    monkeypatch.setenv("HIS_MASTER_CHATBOT_SERVICE_KEY", "test-service-key")
    return secret, {"X-Master-Chatbot-Service-Key": "test-service-key"}


async def _clarification_workflow(state):  # noqa: ANN001
    return {
        "response_message": "Please clarify your request.",
        "data": [],
        "metadata": {"app_id": "his", "route": None},
    }


def test_health_endpoint() -> None:
    transport = httpx.ASGITransport(app=app)
    response = asyncio.run(_request(transport, "GET", "/health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "master-chatbot"}


def test_chat_response_allows_null_intent(monkeypatch) -> None:
    _configure_his_auth(monkeypatch)

    monkeypatch.setattr("app.main.verify_hs256_jwt", lambda authorization, secret, algorithm: {"sub": "user-1"})
    monkeypatch.setattr("app.main.workflow.run", _clarification_workflow)

    transport = httpx.ASGITransport(app=app)
    response = asyncio.run(
        _request(
            transport,
            "POST",
            "/api/v1/chat",
            json={"app_id": "his", "message": "show me recent updates"},
            headers={
                "Authorization": "Bearer test-token",
                "X-Master-Chatbot-Service-Key": "test-service-key",
            },
        )
    )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] is None
    assert body["data"] == []
    assert body["message"] == "Please clarify your request."


def test_chat_accepts_valid_his_jwt(monkeypatch) -> None:
    secret, headers = _configure_his_auth(monkeypatch)
    monkeypatch.setattr("app.main.workflow.run", _clarification_workflow)
    headers["Authorization"] = f"Bearer {_hs256_token(secret)}"

    response = asyncio.run(
        _request(
            httpx.ASGITransport(app=app),
            "POST",
            "/api/v1/chat",
            json={"app_id": "his", "message": "hello"},
            headers=headers,
        )
    )

    assert response.status_code == 200


def test_chat_rejects_missing_or_invalid_his_jwt(monkeypatch) -> None:
    secret, headers = _configure_his_auth(monkeypatch)
    monkeypatch.setattr("app.main.workflow.run", _clarification_workflow)

    missing = asyncio.run(
        _request(
            httpx.ASGITransport(app=app),
            "POST",
            "/api/v1/chat",
            json={"app_id": "his", "message": "hello"},
            headers=headers,
        )
    )
    invalid = asyncio.run(
        _request(
            httpx.ASGITransport(app=app),
            "POST",
            "/api/v1/chat",
            json={"app_id": "his", "message": "hello"},
            headers={**headers, "Authorization": f"Bearer {_hs256_token(secret + '-wrong')}"},
        )
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401


def test_chat_rejects_invalid_service_key_before_jwt_verification(monkeypatch) -> None:
    secret, _ = _configure_his_auth(monkeypatch)
    monkeypatch.setattr("app.main.workflow.run", _clarification_workflow)

    response = asyncio.run(
        _request(
            httpx.ASGITransport(app=app),
            "POST",
            "/api/v1/chat",
            json={"app_id": "his", "message": "hello"},
            headers={
                "Authorization": f"Bearer {_hs256_token(secret)}",
                "X-Master-Chatbot-Service-Key": "wrong-service-key",
            },
        )
    )

    assert response.status_code == 403


def test_registration_api_manages_only_the_target_application(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    registry = ApplicationRegistry(tmp_path / "applications.json")
    monkeypatch.setattr("app.main.application_registry", registry)
    monkeypatch.setenv("MASTER_CHATBOT_REGISTRATION_KEY", "registration-key")
    payload = {
        "app_id": "ecommerce",
        "name": "ShopNest",
        "base_url": "http://shop.test:8000",
        "jwt_secret_env": "SECRET_KEY",
        "jwt_algorithm": "HS256",
        "service_key_env": "ECOMMERCE_MASTER_CHATBOT_SERVICE_KEY",
        "openapi_url": "http://shop.test:8000/openapi.json",
        "routes": [{
            "name": "list_orders",
            "method": "GET",
            "path": "/api/v1/orders",
            "description": "List orders",
            "parameters": {},
        }],
    }
    registered = asyncio.run(register_application(ApplicationRegistrationRequest(**payload), None))
    synchronized = asyncio.run(sync_application_routes("ecommerce", RouteSyncRequest(routes=[{
        "name": "get_cart", "method": "GET", "path": "/api/v1/cart", "description": "Get cart", "parameters": {},
    }]), None))

    assert registered["route_count"] == 1
    assert synchronized["route_count"] == 1
    assert registry.get("ecommerce").routes[0].name == "get_cart"
    removed = asyncio.run(unregister_application("ecommerce", None))
    assert removed == {"success": True}


def test_registration_api_rejects_invalid_registration_key(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    monkeypatch.setenv("MASTER_CHATBOT_REGISTRATION_KEY", "registration-key")
    with pytest.raises(HTTPException) as exc_info:
        _require_registration_key("wrong-key")

    assert exc_info.value.status_code == 403


async def _request(transport: httpx.ASGITransport, method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def test_retried_request_reuses_response_and_conversation(monkeypatch):
    _configure_his_auth(monkeypatch)
    monkeypatch.setattr("app.main.verify_hs256_jwt", lambda *args, **kwargs: {"sub": "dedupe-user"})
    calls = []
    async def run(state):
        calls.append(state)
        return {"response_message": "Done", "data": [], "metadata": {"route": None}}
    monkeypatch.setattr("app.main.workflow.run", run)
    async def exercise():
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test", "X-Master-Chatbot-Service-Key": "test-service-key"}
        payload = {"app_id": "his", "message": "do this", "session_id": "dedupe-session", "request_id": "dedupe-request"}
        first = await _request(transport, "POST", "/api/v1/chat", headers=headers, json=payload)
        second = await _request(transport, "POST", "/api/v1/chat", headers=headers, json=payload)
        conflict = await _request(transport, "POST", "/api/v1/chat", headers=headers, json={**payload, "message": "different action"})
        return first, second, conflict
    first, second, conflict = asyncio.run(exercise())
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(calls) == 1
    assert conflict.status_code == 409
