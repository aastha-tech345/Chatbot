"""Request credentials stay outside graph state and reach every HTTP method."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from app.api_client import ApplicationAPIClient
from app.authorization import authenticate, auth_request, normalize_authorization, user_authorization
from app.models import ApplicationDefinition, AuthenticationConfig, RouteDefinition
from app.app_registry import application_registry


def application(route):
    return ApplicationDefinition(app_id="ecommerce", name="ShopNest", base_url="http://shopnest.test",
                                 service_key_env="TEST_SERVICE_KEY", routes=[route], authentication=AuthenticationConfig(
                                     verification="introspection", user_info_path="/api/v1/auth/me"))


@pytest.mark.parametrize("protected,token", [(True, "test-user-secret"), (False, None), (True, None)])
@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("upstream_status", [200, 401, 403])
def test_forwarding(monkeypatch, caplog, method, upstream_status, protected, token):
    from app import database, repositories
    route = RouteDefinition(name="customer_action", method=method, path="/api/v1/customer",
                            description="Customer action", requires_auth=protected, visibility="private" if protected else "public")
    app = application(route)
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(
        is_enabled=True, status="active"))
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(repositories.ApplicationRepo, "get_by_app_id", AsyncMock(
        return_value=SimpleNamespace(id="app", is_enabled=True)))
    monkeypatch.setattr(application_registry, "get_service_key", lambda _: "test-service-secret")
    client = ApplicationAPIClient()
    client._record_log = AsyncMock()
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(upstream_status, json={"detail": "test-user-secret", "items": []})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(
        transport=httpx.MockTransport(handler), **kw))
    async def execute():
        return await client.execute(application=app, route=route, parameters={},
                                    authorization=token, request_id="test")
    if protected and not token:
        with pytest.raises(HTTPException) as error:
            asyncio.run(execute())
        assert error.value.status_code == 401
        assert not calls
        return
    if upstream_status == 200:
        asyncio.run(execute())
    else:
        with pytest.raises(HTTPException) as error:
            asyncio.run(execute())
        assert error.value.status_code == upstream_status
        assert "test-user-secret" not in str(error.value.detail)
    assert calls[0].headers.get("Authorization") == ("Bearer test-user-secret" if protected else None)
    assert calls[0].headers["X-Master-Chatbot-Service-Key"] == "test-service-secret"
    assert "test-user-secret" not in caplog.text
    assert "test-service-secret" not in caplog.text
    assert "test-user-secret" not in str(client._record_log.call_args)


def test_normalization_and_sign_in():
    assert normalize_authorization("abc") == "Bearer abc"
    assert normalize_authorization("Bearer abc") == "Bearer abc"
    assert normalize_authorization("  ") is None
    app = application(RouteDefinition(name="cart", method="POST", path="/cart", description="Cart"))
    assert auth_request(app)["execution_error"] == "Please sign in to your ShopNest account first to use this feature."
    assert "session has expired" in auth_request(app, expired=True)["execution_error"]


def test_introspection_uses_existing_shopnest_session(monkeypatch):
    app = application(RouteDefinition(name="cart", method="POST", path="/cart", description="Cart"))
    real_client = httpx.AsyncClient
    def handler(request):
        assert request.url.path == "/api/v1/auth/me"
        assert request.headers["Authorization"] == "Bearer test-user"
        return httpx.Response(200, json={"id": "customer-1", "roles": ["customer"]})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    result = asyncio.run(authenticate(app, "test-user"))
    assert result.authenticated and result.user_id == "customer-1"


def test_graph_state_has_no_token():
    from app.workflow import ChatState
    assert "authorization" not in ChatState.__annotations__
    async def request(token):
        context = user_authorization.set(token)
        try:
            await asyncio.sleep(0)
            assert user_authorization.get() == token
        finally:
            user_authorization.reset(context)
    async def concurrent():
        await asyncio.gather(request("first"), request("second"))
        assert user_authorization.get() is None
    asyncio.run(concurrent())


@pytest.mark.parametrize("key", [None, "wrong"])
def test_missing_or_wrong_service_key(monkeypatch, key):
    from app.main import _require_app_service
    monkeypatch.setattr(application_registry, "get_service_key", lambda _: "expected")
    app = application(RouteDefinition(name="cart", method="POST", path="/cart", description="Cart"))
    with pytest.raises(HTTPException) as error:
        _require_app_service(app, key)
    assert error.value.status_code == 403


def test_chat_keeps_credentials_out_of_workflow_and_conversation(monkeypatch):
    from app import main
    from app.authorization import AuthState
    app = application(RouteDefinition(name="cart", method="POST", path="/cart", description="Cart"))
    monkeypatch.setattr(main.application_registry, "get", lambda _: app)
    monkeypatch.setattr(main.application_registry, "get_service_key", lambda _: "service-test")
    monkeypatch.setattr(main, "authenticate", AsyncMock(return_value=AuthState("ecommerce", True, "test-customer")))
    async def run(state):
        assert "authorization" not in state
        assert "request-only-token" not in str(state)
        assert user_authorization.get() == "Bearer request-only-token"
        return {"response_message": "Done", "data": [], "metadata": {"app_id": "ecommerce"}}
    monkeypatch.setattr(main.workflow, "run", run)
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            response = await client.post("/api/v1/chat", headers={
                "Authorization": "request-only-token", "X-Master-Chatbot-Service-Key": "service-test",
            }, json={"app_id": "ecommerce", "message": "show my cart"})
        assert response.status_code == 200
        assert "request-only-token" not in response.text
        assert user_authorization.get() is None
        assert "request-only-token" not in str(main.conversations.entries)
    asyncio.run(request())


def test_legacy_shopnest_registration_uses_identity_api():
    from app.app_registry import ApplicationRegistry
    db_app = SimpleNamespace(id="app", app_id="ecommerce", name="ShopNest", base_url="http://shopnest.test",
                             auth_config_json=None, chatbot_config_json=None, jwt_algorithm="HS256",
                             discovery_mode="manual", openapi_url=None)
    credentials = SimpleNamespace(list_for_app=AsyncMock(return_value=[]))
    routes = SimpleNamespace(list_for_app=AsyncMock(return_value=[]))
    app, _ = asyncio.run(ApplicationRegistry()._build_definition(db_app, credentials, routes, lambda value: value))
    assert app.authentication.verification == "introspection"
    assert app.authentication.user_info_path == "/api/v1/auth/me"
