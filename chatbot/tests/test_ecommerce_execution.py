"""Contract tests for Master Chatbot's registered E-commerce API routes."""

from __future__ import annotations

import asyncio
import sys

import httpx
import pytest
from fastapi import HTTPException

sys.path.insert(0, "chatbot/backend")

from app.api_client import ApplicationAPIClient
from app.models import ApplicationDefinition, RouteDefinition
from app import api_client as api_client_module


class RecordingAsyncClient:
    """Captures the application API request without contacting a database."""

    calls: list[dict[str, object]] = []

    def __init__(self, **_: object) -> None:
        pass

    async def __aenter__(self) -> "RecordingAsyncClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        return httpx.Response(200, json={"items": [{"slug": "running-shoe"}]})


class StatusAsyncClient:
    status_code = 401

    def __init__(self, **_: object) -> None:
        pass

    async def __aenter__(self) -> "StatusAsyncClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def request(self, method: str, url: str, **_: object) -> httpx.Response:
        return httpx.Response(self.status_code, json={"detail": "authentication failed"})


def test_registered_ecommerce_product_route_reaches_shopnest_api(monkeypatch) -> None:
    RecordingAsyncClient.calls = []
    monkeypatch.setattr(api_client_module.httpx, "AsyncClient", RecordingAsyncClient)
    route = RouteDefinition(
        name="get_product",
        method="GET",
        path="/api/v1/products/{slug}",
        description="Get a product",
        parameters={"slug": "Product slug"},
    )
    application = ApplicationDefinition(
        app_id="ecommerce",
        name="E-Commerce",
        base_url="http://shopnest.test:8000",
        jwt_secret_env="ECOMMERCE_JWT_SECRET",
        service_key_env="ECOMMERCE_MASTER_CHATBOT_SERVICE_KEY",
        routes=[route],
    )

    result = asyncio.run(
        ApplicationAPIClient().execute(
            application=application,
            route=route,
            parameters={"slug": "running-shoe"},
            authorization="Bearer user-jwt",
            request_id="request-1",
        )
    )

    assert result == {"items": [{"slug": "running-shoe"}]}
    assert RecordingAsyncClient.calls == [
        {
            "method": "GET",
            "url": "http://shopnest.test:8000/api/v1/products/running-shoe",
            "params": {},
            "json": None,
            "headers": {"Authorization": "Bearer user-jwt", "X-Request-Id": "request-1"},
        }
    ]


@pytest.mark.parametrize("status_code", [401, 403])
def test_downstream_auth_errors_are_preserved(monkeypatch, status_code: int) -> None:
    StatusAsyncClient.status_code = status_code
    monkeypatch.setattr(api_client_module.httpx, "AsyncClient", StatusAsyncClient)
    route = RouteDefinition(
        name="list_orders",
        method="GET",
        path="/api/v1/orders",
        description="List orders",
    )
    application = ApplicationDefinition(
        app_id="ecommerce",
        name="E-Commerce",
        base_url="http://shopnest.test:8000",
        jwt_secret_env="ECOMMERCE_JWT_SECRET",
        service_key_env="ECOMMERCE_MASTER_CHATBOT_SERVICE_KEY",
        routes=[route],
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            ApplicationAPIClient().execute(
                application=application,
                route=route,
                parameters={},
                authorization="Bearer user-jwt",
                request_id="request-auth-error",
            )
        )
    assert error.value.status_code == status_code
