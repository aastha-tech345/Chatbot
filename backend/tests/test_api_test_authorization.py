from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx

from app import services as services_module
from app.services import ApplicationRouteService, _request_scoped_headers


class FakeRouteRepo:
    auth_required = False
    path = "/api/v1/admin/analytics/summary"

    async def get_by_id(self, route_id: str):
        return SimpleNamespace(
            id=route_id,
            application_id="app-1",
            method="GET",
            path=self.path,
            full_url=None,
            headers_json=None,
            query_params_json=None,
            request_body_json=None,
            content_type=None,
            auth_required=self.auth_required,
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
        if url.endswith("/api/v1/admin/coupons"):
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"total_orders": 39})


def _service() -> ApplicationRouteService:
    service = ApplicationRouteService(db=None)  # type: ignore[arg-type]
    service.route_repo = FakeRouteRepo()  # type: ignore[assignment]
    service.app_repo = FakeAppRepo()  # type: ignore[assignment]
    return service


def _run_test_request(
    headers: dict[str, str] | None,
    *,
    auth_required: bool = False,
    path: str = "/api/v1/admin/analytics/summary",
):
    RecordingAsyncClient.calls = []
    services_module.httpx.AsyncClient = RecordingAsyncClient  # type: ignore[assignment]
    service = _service()
    service.route_repo.auth_required = auth_required  # type: ignore[attr-defined]
    service.route_repo.path = path  # type: ignore[attr-defined]
    return asyncio.run(service.test_route("route-1", headers=headers))


def test_raw_authorization_token_gets_bearer_prefix() -> None:
    _run_test_request({"Authorization": "eyJabc"})

    assert RecordingAsyncClient.calls[0]["headers"]["Authorization"] == "Bearer eyJabc"


def test_bearer_authorization_token_is_not_doubled() -> None:
    _run_test_request({"Authorization": "Bearer eyJabc"})

    assert RecordingAsyncClient.calls[0]["headers"]["Authorization"] == "Bearer eyJabc"


def test_changed_authorization_header_uses_new_value() -> None:
    _run_test_request({"Authorization": "Bearer old-token"})
    _run_test_request({"Authorization": "Bearer new-token"})

    assert RecordingAsyncClient.calls[0]["headers"]["Authorization"] == "Bearer new-token"


def test_missing_authorization_header_stays_absent() -> None:
    _run_test_request({})

    assert "Authorization" not in RecordingAsyncClient.calls[0]["headers"]


def test_missing_authorization_header_reports_required_for_auth_route() -> None:
    result = _run_test_request({}, auth_required=True)

    assert result["status_code"] == 401
    assert result["body"] == {"detail": "Authorization header is required for this endpoint."}
    assert RecordingAsyncClient.calls == []


def test_full_jwt_like_authorization_value_is_preserved() -> None:
    full_token = "eyJ" + ("a" * 512) + ".eyJ" + ("b" * 512) + ".sig" + ("c" * 256)

    _run_test_request({"Authorization": full_token})

    assert RecordingAsyncClient.calls[0]["headers"]["Authorization"] == f"Bearer {full_token}"


def test_request_scoped_authorization_is_canonical_even_with_lowercase_key() -> None:
    headers = _request_scoped_headers({"authorization": "eyJabc"})

    assert headers == {"Authorization": "Bearer eyJabc"}


def test_connected_app_receives_authorization_header() -> None:
    result = _run_test_request({"Authorization": "Bearer super-admin-token"})

    assert result["status_code"] == 200
    assert RecordingAsyncClient.calls[0]["url"] == "http://ecommerce.test/api/v1/admin/analytics/summary"
    assert RecordingAsyncClient.calls[0]["headers"]["Authorization"] == "Bearer super-admin-token"


def test_empty_array_response_is_successfully_returned() -> None:
    result = _run_test_request(
        {"Authorization": "Bearer super-admin-token"},
        path="/api/v1/admin/coupons",
    )

    assert result["success"] is True
    assert result["status_code"] == 200
    assert result["body"] == []
    assert RecordingAsyncClient.calls[0]["url"] == "http://ecommerce.test/api/v1/admin/coupons"
