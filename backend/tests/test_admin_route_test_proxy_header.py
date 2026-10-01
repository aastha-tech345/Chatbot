from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from starlette.requests import Request

from app import admin_routes


class FakeRouteRepo:
    async def get_by_id(self, route_id: str):
        return SimpleNamespace(
            id=route_id,
            application_id="app-1",
            method="GET",
            path="/api/v1/admin/coupons",
            full_url=None,
            headers_json=None,
            query_params_json=None,
            request_body_json=None,
            content_type=None,
            auth_required=True,
        )


class FakeAppRepo:
    async def get_by_id(self, app_id: str):
        return SimpleNamespace(id=app_id, base_url="http://ecommerce.test")


class RecordingAsyncClient:
    calls: list[dict] = []

    def __init__(self, **_: object) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        return httpx.Response(200, json=[])


@pytest.mark.asyncio
async def test_route_test_proxy_header_becomes_downstream_authorization(monkeypatch) -> None:
    from app import services as services_module
    from app.services import ApplicationRouteService

    def fake_service(db):
        service = ApplicationRouteService(db=None)  # type: ignore[arg-type]
        service.route_repo = FakeRouteRepo()  # type: ignore[assignment]
        service.app_repo = FakeAppRepo()  # type: ignore[assignment]
        return service

    RecordingAsyncClient.calls = []
    monkeypatch.setattr(admin_routes, "ApplicationRouteService", fake_service)
    monkeypatch.setattr(services_module.httpx, "AsyncClient", RecordingAsyncClient)

    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/v1/admin/routes/route-1/test",
        "headers": [(b"x-api-test-authorization", b"Bearer super-admin-token")],
    })
    response = await admin_routes.test_manual_route(
        "route-1",
        request,
        admin_routes.RouteTestRequest(method="GET", headers={}),
        admin_id="admin-1",
        db=None,  # type: ignore[arg-type]
    )

    assert response["status_code"] == 200
    assert response["body"] == []
    assert RecordingAsyncClient.calls[0]["headers"]["Authorization"] == "Bearer super-admin-token"
