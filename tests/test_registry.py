import json
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, "chatbot/backend")
from app.app_registry import ApplicationRegistry
from app.api_client import ApplicationAPIClient
from app.models import ApplicationDefinition, RouteDefinition
from app.tool_registry import DynamicToolRegistry


def test_registry_exposes_only_declared_route(tmp_path) -> None:
    registry_file = tmp_path / "applications.json"
    registry_file.write_text(json.dumps({"applications": [{
        "app_id": "sample", "name": "Sample", "base_url": "http://example.test",
        "jwt_secret_env": "SAMPLE_JWT", "service_key_env": "SAMPLE_SERVICE_KEY",
        "routes": [{"name": "list_records", "method": "GET", "path": "/api/records", "description": "List records", "parameters": {"name": "Name"}}],
    }]}), encoding="utf-8")
    registry = ApplicationRegistry(registry_file)
    application = registry.get("sample")
    assert registry.route(application, "list_records").path == "/api/records"
    try:
        registry.route(application, "delete_everything")
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("unregistered route was accepted")

    tools = DynamicToolRegistry(ApplicationAPIClient()).build(
        application=application,
        authorization="Bearer test-token",
        request_id="test-request",
    )
    assert list(tools) == ["list_records"]
    assert tools["list_records"].name == "sample_list_records"


def test_registry_accepts_standard_mutating_methods(tmp_path) -> None:
    registry_file = tmp_path / "applications.json"
    registry_file.write_text(json.dumps({"applications": [{
        "app_id": "sample", "name": "Sample", "base_url": "http://example.test",
        "jwt_secret_env": "SAMPLE_JWT", "service_key_env": "SAMPLE_SERVICE_KEY",
        "routes": [
            {"name": "update_record", "method": "PUT", "path": "/api/records/{id}", "description": "Update record", "parameters": {"id": "ID"}},
            {"name": "patch_record", "method": "PATCH", "path": "/api/records/{id}", "description": "Patch record", "parameters": {"id": "ID"}},
            {"name": "delete_record", "method": "DELETE", "path": "/api/records/{id}", "description": "Delete record", "parameters": {"id": "ID"}}
        ],
    }]}), encoding="utf-8")

    registry = ApplicationRegistry(registry_file)
    application = registry.get("sample")

    assert registry.route(application, "update_record").method.value == "PUT"
    assert registry.route(application, "patch_record").method.value == "PATCH"
    assert registry.route(application, "delete_record").method.value == "DELETE"


def test_registry_upsert_and_unregister_preserve_other_applications(tmp_path) -> None:
    registry_file = tmp_path / "applications.json"
    registry_file.write_text(json.dumps({"applications": [
        {"app_id": "his", "name": "HIS", "base_url": "http://his.test", "jwt_secret_env": "HIS_JWT", "service_key_env": "HIS_KEY", "routes": [{"name": "list_patients", "method": "GET", "path": "/patients", "description": "Patients"}]},
        {"app_id": "hrm", "name": "HRM", "base_url": "http://hrm.test", "jwt_secret_env": "HRM_JWT", "service_key_env": "HRM_KEY", "routes": [{"name": "list_employees", "method": "GET", "path": "/employees", "description": "Employees"}]},
    ]}), encoding="utf-8")
    registry = ApplicationRegistry(registry_file)
    ecommerce = ApplicationDefinition(
        app_id="ecommerce", name="ShopNest", base_url="http://shop.test", jwt_secret_env="SECRET_KEY",
        service_key_env="ECOMMERCE_MASTER_CHATBOT_SERVICE_KEY",
        routes=[RouteDefinition(name="list_orders", method="GET", path="/api/v1/orders", description="Orders")],
    )

    registry.upsert(ecommerce)
    assert registry.status("ecommerce")["route_count"] == 1
    assert registry.get("his").name == "HIS"
    assert registry.get("hrm").name == "HRM"

    registry.unregister("ecommerce")
    assert registry.get("his").name == "HIS"
    with pytest.raises(HTTPException) as exc_info:
        registry.unregister("ecommerce")
    assert exc_info.value.status_code == 404
