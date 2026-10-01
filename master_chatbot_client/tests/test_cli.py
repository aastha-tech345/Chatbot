"""Tests for SDK registration CLI and safe OpenAPI discovery."""

from __future__ import annotations

import pytest
import httpx

from master_chatbot import cli
from master_chatbot.discovery import OpenAPIDiscoveryError, discover_application_routes, discover_routes


def _configure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASTER_CHATBOT_URL", "http://master.test:9000/api/v1")
    monkeypatch.setenv("MASTER_CHATBOT_APP_ID", "ecommerce")
    monkeypatch.setenv("MASTER_CHATBOT_SERVICE_KEY", "runtime-service-key")
    monkeypatch.setenv("MASTER_CHATBOT_REGISTRATION_KEY", "registration-key")
    monkeypatch.setenv("MASTER_CHATBOT_API_BASE_URL", "http://shop.test:8000")


class Response:
    def __init__(self, body: object, status_code: int = 200) -> None:
        self.body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://shop.test/openapi.json")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> object:
        return self.body


def test_discovery_filters_unsafe_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/api/v1/orders": {
                "get": {
                    "operationId": "list_orders",
                    "summary": "Orders",
                    "x-master-chatbot": {"enabled": True},
                }
            },
            "/api/v1/admin/orders": {
                "get": {
                    "operationId": "admin_orders",
                    "x-master-chatbot": {"enabled": True},
                }
            },
            "/api/v1/master-chatbot/chat": {
                "post": {
                    "operationId": "bridge",
                    "x-master-chatbot": {"enabled": True, "allow_write": True},
                }
            },
            "/api/v1/cart": {
                "delete": {
                    "operationId": "clear_cart",
                    "x-master-chatbot": {"enabled": True},
                }
            },
            "/api/v1/products/{slug}": {
                "get": {
                    "operationId": "product_detail",
                    "x-master-chatbot": {"enabled": True, "description": "Get product details"},
                    "parameters": [{"name": "slug", "in": "path", "description": "Product slug"}],
                }
            },
        }
    }
    monkeypatch.setattr("master_chatbot.discovery.httpx.get", lambda *args, **kwargs: Response(document))

    routes = discover_routes("http://shop.test:8000/openapi.json")

    assert routes == [
        {
            "name": "list_orders",
            "method": "GET",
            "path": "/api/v1/orders",
            "description": "Orders",
            "parameters": {},
        },
        {
            "name": "product_detail",
            "method": "GET",
            "path": "/api/v1/products/{slug}",
            "description": "Get product details",
            "parameters": {"slug": "Product slug"},
        },
    ]


@pytest.mark.parametrize("command, method, suffix", [
    ("register", "POST", "/register"),
    ("sync", "PUT", "/ecommerce/routes"),
    ("status", "GET", "/ecommerce"),
    ("unregister", "DELETE", "/ecommerce"),
])
def test_cli_commands(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: str, method: str, suffix: str) -> None:
    _configure(monkeypatch)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "master_chatbot.cli.discover_application_routes",
        lambda *_args, **_kwargs: (
            "http://shop.test:8000/openapi.json",
            [{"name": "list_orders", "method": "GET", "path": "/api/v1/orders", "description": "Orders", "parameters": {}}],
        ),
    )

    def request(method_name: str, url: str, **kwargs: object) -> Response:
        calls.append({"method": method_name, "url": url, **kwargs})
        return Response({"app_id": "ecommerce", "name": "ShopNest", "base_url": "http://shop.test:8000", "enabled": True, "route_count": 1})

    monkeypatch.setattr("master_chatbot.cli.httpx.request", request)

    assert cli.run([command]) == 0
    assert calls[0]["method"] == method
    assert str(calls[0]["url"]).endswith(suffix)
    assert "runtime-service-key" not in capsys.readouterr().out


def test_cli_rejects_missing_runtime_service_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
    monkeypatch.delenv("MASTER_CHATBOT_SERVICE_KEY")

    with pytest.raises(cli.RegistrationCLIError, match="MASTER_CHATBOT_SERVICE_KEY"):
        cli.RegistrationConfig.from_env(require_api_base_url=False)


def test_cli_rejects_missing_master_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
    monkeypatch.delenv("MASTER_CHATBOT_URL")

    with pytest.raises(cli.RegistrationCLIError, match="MASTER_CHATBOT_URL"):
        cli.RegistrationConfig.from_env(require_api_base_url=False)


def test_cli_rejects_invalid_application_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setenv("MASTER_CHATBOT_APP_ID", "E-commerce")

    with pytest.raises(cli.RegistrationCLIError, match="invalid"):
        cli.RegistrationConfig.from_env(require_api_base_url=False)


def test_openapi_discovery_failure_is_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*_: object, **__: object) -> Response:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("master_chatbot.discovery.httpx.get", unavailable)

    with pytest.raises(OpenAPIDiscoveryError, match="OpenAPI"):
        discover_routes("http://shop.test:8000/openapi.json")


def test_discovery_uses_root_openapi_document(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def get(url: str, **_: object) -> Response:
        calls.append(url)
        return Response({"openapi": "3.1.0", "paths": {}})

    monkeypatch.setattr("master_chatbot.discovery.httpx.get", get)

    openapi_url, routes = discover_application_routes("http://shop.test:8000/")

    assert openapi_url == "http://shop.test:8000/openapi.json"
    assert routes == []
    assert calls == ["http://shop.test:8000/openapi.json"]


def test_discovery_falls_back_to_configured_api_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def get(url: str, **_: object) -> Response:
        calls.append(url)
        if url == "http://shop.test:8000/openapi.json":
            return Response({}, status_code=404)
        return Response({"openapi": "3.1.0", "paths": {}})

    monkeypatch.setattr("master_chatbot.discovery.httpx.get", get)

    openapi_url, _ = discover_application_routes("http://shop.test:8000", api_prefix="/api/v1")

    assert openapi_url == "http://shop.test:8000/api/v1/openapi.json"
    assert calls == [
        "http://shop.test:8000/openapi.json",
        "http://shop.test:8000/api/v1/openapi.json",
    ]


def test_discovery_supports_custom_prefix_and_normalizes_slashes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def get(url: str, **_: object) -> Response:
        calls.append(url)
        if url == "http://shop.test:8000/openapi.json":
            raise httpx.ConnectError("not found")
        return Response({"openapi": "3.1.0", "paths": {}})

    monkeypatch.setattr("master_chatbot.discovery.httpx.get", get)

    openapi_url, _ = discover_application_routes("http://shop.test:8000///", api_prefix="///public/v2///")

    assert openapi_url == "http://shop.test:8000/public/v2/openapi.json"
    assert all("//openapi.json" not in url for url in calls)


def test_discovery_uses_openapi_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def get(url: str, **_: object) -> Response:
        calls.append(url)
        return Response({"openapi": "3.1.0", "paths": {}})

    monkeypatch.setattr("master_chatbot.discovery.httpx.get", get)

    openapi_url, _ = discover_application_routes(
        "http://shop.test:8000",
        openapi_url="http://schema.test:7001/docs/openapi.json/",
        api_prefix="/api/v1",
    )

    assert openapi_url == "http://schema.test:7001/docs/openapi.json"
    assert calls == ["http://schema.test:7001/docs/openapi.json"]


def test_discovery_rejects_invalid_openapi_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "master_chatbot.discovery.httpx.get",
        lambda *_args, **_kwargs: Response({"paths": {}}),
    )

    with pytest.raises(OpenAPIDiscoveryError, match="OpenAPI"):
        discover_application_routes("http://shop.test:8000")


def test_discovery_rejects_invalid_openapi_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class InvalidJSONResponse(Response):
        def json(self) -> object:
            raise ValueError("malformed JSON")

    monkeypatch.setattr(
        "master_chatbot.discovery.httpx.get",
        lambda *_args, **_kwargs: InvalidJSONResponse({}),
    )

    with pytest.raises(OpenAPIDiscoveryError, match="invalid JSON"):
        discover_application_routes("http://shop.test:8000")


def test_discovery_reports_attempted_url_and_http_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def not_found(*_: object, **__: object) -> Response:
        return Response({}, status_code=404)

    monkeypatch.setattr("master_chatbot.discovery.httpx.get", not_found)

    with pytest.raises(OpenAPIDiscoveryError, match=r"shop\.test:8000/openapi\.json: HTTP 404"):
        discover_application_routes("http://shop.test:8000")


def test_discovery_fails_when_all_candidates_are_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*_: object, **__: object) -> Response:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("master_chatbot.discovery.httpx.get", unavailable)

    with pytest.raises(OpenAPIDiscoveryError, match="OpenAPI"):
        discover_application_routes("http://shop.test:8000", api_prefix="/api/v1")
