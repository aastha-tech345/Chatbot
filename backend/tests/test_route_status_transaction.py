"""Route toggles must be committed before a separate registry session reads them."""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.app_registry import ApplicationRegistry
from app.database import Base
from app.db_models import Application, ApplicationRoute
from app.models import RouteStatus
from app.route_selector import RouteSelector
from app.services import ApplicationRouteService


@pytest.mark.asyncio
async def test_repeated_toggles_refresh_registry_before_request_cleanup(tmp_path):
    # A file database gives the writer and registry independent transactions.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'routes.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    registry = ApplicationRegistry()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add(Application(id="app-1", app_id="catalog", name="Catalog",
                               base_url="https://example.com", discovery_mode="manual"))
            db.add(ApplicationRoute(id="route-1", application_id="app-1", method="GET",
                                    path="/products", operation_id="get_products",
                                    description="Get products", is_enabled=True,
                                    status=RouteStatus.AVAILABLE.value))
            await db.commit()

        with patch("app.database.AsyncSessionLocal", sessions), patch(
            "app.app_registry.application_registry", registry
        ):
            await registry.reload()
            assert len(registry.get("catalog").routes) == 1
            for enabled in [False, True] * 4:
                async with sessions() as db:
                    await ApplicationRouteService(db).update_route_status("route-1", enabled)
                    # Assert before get_db's end-of-request commit could hide the bug.
                    selected, _ = RouteSelector().select(registry.get("catalog"), "show products")
                    assert ("get_products" in {route.name for route in selected}) is enabled
                    async with sessions() as reader:
                        saved = await reader.get(ApplicationRoute, "route-1")
                        assert saved.is_enabled is enabled
                        assert saved.status == (RouteStatus.AVAILABLE if enabled else RouteStatus.DISABLED)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_failed_commit_does_not_publish_route_status():
    db = AsyncMock()
    db.commit.side_effect = RuntimeError("commit failed")
    service = ApplicationRouteService(db)
    service.route_repo = AsyncMock()
    service.audit = AsyncMock()
    with patch("app.app_registry.application_registry") as registry:
        registry.reload = AsyncMock()
        with pytest.raises(RuntimeError, match="commit failed"):
            await service.update_route_status("route-1", True)
        registry.reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_refreshes_other_workers_routes_in_same_conversation(tmp_path, monkeypatch):
    import httpx
    from app import main
    from app.admin_auth import require_admin
    from app.database import get_db
    from app.conversations import ConversationStore
    from app.crypto import encrypt
    from app.db_models import ApplicationCredential

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'workers.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setenv("SECRET_KEY", "test-only-encryption-key-32-bytes!")
    admin_registry = ApplicationRegistry()
    chat_registry = ApplicationRegistry()
    monkeypatch.setattr("app.database.AsyncSessionLocal", sessions)
    # Model separate processes: admin refresh cannot update the chat worker's cache.
    monkeypatch.setattr("app.app_registry.application_registry", admin_registry)
    monkeypatch.setattr(main, "application_registry", chat_registry)
    monkeypatch.setattr(main, "conversations", ConversationStore())

    async def db_override():
        async with sessions() as db:
            yield db
            await db.commit()

    from types import SimpleNamespace
    from app.planner import RoutePlanner
    from app.workflow import ChatWorkflow
    from app.api_client import ApplicationAPIClient

    prompts = []
    product_requests = []

    async def model_reply(prompt):
        # Stub only the external LLM; run actual selection, validation, graph and tools.
        prompts.append(prompt)
        catalog = prompt.split("Routes (* = required param):\n", 1)[1].split("User request:", 1)[0]
        available = "get_products" in catalog
        return SimpleNamespace(content=(
            '{"route_name":"get_products","parameters":{}}' if available else
            '{"route_name":null,"parameters":{},"clarification":"Route unavailable"}'
        ))

    model = SimpleNamespace(ainvoke=AsyncMock(side_effect=model_reply))
    monkeypatch.setattr("app.planner.create_chat_model", AsyncMock(return_value=model))
    monkeypatch.setattr(main, "workflow", ChatWorkflow(chat_registry, RoutePlanner(), ApplicationAPIClient()))
    real_send = httpx.AsyncClient.send

    async def send(client, request, **kwargs):
        if request.url.host == "example.com":
            assert request.method == "GET" and request.url.path == "/products"
            product_requests.append(request)
            return httpx.Response(200, json={"items": [{"id": "product-1", "name": "Test product", "price": 10}]}, request=request)
        return await real_send(client, request, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    monkeypatch.setitem(main.app.dependency_overrides, get_db, db_override)
    monkeypatch.setitem(main.app.dependency_overrides, require_admin, lambda: None)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add(Application(id="app-1", app_id="catalog", name="Catalog",
                               base_url="https://example.com", discovery_mode="manual"))
            db.add(ApplicationRoute(id="route-1", application_id="app-1", method="GET",
                                    path="/products", operation_id="get_products",
                                    description="Get products", is_enabled=True,
                                    status=RouteStatus.AVAILABLE.value))
            await db.commit()
        async with sessions() as db:
            db.add(ApplicationCredential(application_id="app-1", auth_type="service_key",
                                         bearer_token_encrypted=encrypt("test-route-key")))
            await db.commit()
        await admin_registry.reload()
        await chat_registry.reload()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test",
                                     headers={"X-Master-Chatbot-Service-Key": "test-route-key"}) as client:
            for index, enabled in enumerate([False, True] * 4):
                result = await client.put("/api/v1/admin/routes/route-1/status", json={"is_enabled": enabled})
                assert result.status_code == 200, result.text
                # The chat worker still holds the previous state before the new request.
                assert bool(chat_registry.get("catalog").routes) is not enabled
                response = await client.post("/api/v1/chat", json={
                    "app_id": "catalog", "message": "All products", "session_id": "same-session",
                    "conversation_id": "same-conversation", "request_id": f"turn-{index}",
                })
                assert response.status_code == 200, response.text
                assert bool(response.json()["data"]) is enabled, response.text
                assert bool(chat_registry.get("catalog").routes) is enabled
                assert len(product_requests) == (index + 1) // 2
                if index:
                    assert "Prior conversation" in prompts[-1]

            # Disabling the application must also invalidate a previously loaded worker.
            async with sessions() as db:
                application = await db.get(Application, "app-1")
                application.is_enabled = False
                await db.commit()
            response = await client.post("/api/v1/chat", json={"app_id": "catalog", "message": "All products"})
            assert response.status_code == 400
            assert "APPLICATION_NOT_FOUND" in response.json()["detail"]
            assert "catalog" not in chat_registry._applications
    finally:
        await engine.dispose()


@pytest.mark.parametrize("auth_required", [False, True])
def test_db_route_reload_preserves_access_contract(auth_required):
    from types import SimpleNamespace

    row = SimpleNamespace(
        id="route-1", method="GET", path="/products", operation_id="get_products",
        name="get_products", description="Get products", summary=None,
        parameters_json={}, query_params_json={}, path_params_json={},
        auth_required=auth_required, auth_type=None, source="openapi",
        is_enabled=True, status="Available",
    )
    route = ApplicationRegistry()._route_from_db("catalog", row)
    assert route.requires_auth is auth_required
    assert route.protected is auth_required
    assert route.visibility == ("private" if auth_required else "public")
