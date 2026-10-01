"""Tests for the customer-safe E-commerce application contract."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

sys.path.insert(0, "chatbot/backend")

from app.app_registry import ApplicationRegistry
from app.models import ApplicationDefinition, HTTPMethod, RouteDefinition
from app.planner import RoutePlanner


def test_ecommerce_registration_contains_customer_shopping_routes() -> None:
    registry = ApplicationRegistry()
    application = registry.get("ecommerce")
    routes = {route.name: route for route in application.routes}

    assert application.name == "E-commerce"
    assert application.base_url == "http://localhost:3333"
    assert application.jwt_secret_env == "ECOMMERCE_JWT_SECRET"
    assert application.jwt_algorithm == "HS256"
    assert application.service_key_env == "ECOMMERCE_MASTER_CHATBOT_SERVICE_KEY"
    assert {"his", "hrm"}.issubset(registry._applications)
    assert routes["search_products"].path == "/api/v1/products"
    assert routes["get_product"].path == "/api/v1/products/{slug}"
    assert routes["list_orders"].path == "/api/v1/orders"
    assert routes["track_order_item"].path == "/api/v1/orders/items/{item_id}/tracking"
    assert routes["get_cart"].path == "/api/v1/cart"
    assert routes["list_returns"].path == "/api/v1/returns"
    assert routes["get_wishlist"].path == "/api/v1/wishlist"
    assert routes["list_notifications"].path == "/api/v1/notifications"
    assert routes["get_unread_notification_count"].path == "/api/v1/notifications/unread-count"
    assert {name for name, route in routes.items() if route.method.value != "GET"} == {
        "add_to_cart", "update_cart_item", "add_address", "update_address", "request_return", "cancel_order"
    }
    assert all("/admin/" not in route.path and "/login" not in route.path for route in routes.values())
    assert routes["add_to_cart"].required_parameters == ["product_id", "quantity"]


def test_planner_clarifies_when_a_registered_path_parameter_is_missing(monkeypatch) -> None:
    registry = ApplicationRegistry()
    application = registry.get("ecommerce")

    class Model:
        async def ainvoke(self, _: str) -> SimpleNamespace:
            return SimpleNamespace(content='{"route_name":"track_order_item","parameters":{},"clarification":null}')

    monkeypatch.setattr("app.planner.create_chat_model", lambda: Model())

    plan = asyncio.run(RoutePlanner().plan(message="track my order", application=application))

    assert plan.route_name is None
    assert plan.parameters == {}
    assert plan.clarification == "Please provide the required item_id before I look that up."


def test_planner_asks_for_required_write_fields(monkeypatch):
    class Model:
        async def ainvoke(self, prompt):
            assert 'Integer quantity' in prompt
            return SimpleNamespace(content='{"route_name":"add_to_cart","parameters":{"product_id":"p1"}}')
    monkeypatch.setattr("app.planner.create_chat_model", lambda: Model())
    plan = asyncio.run(RoutePlanner().plan(message="add this", application=ApplicationRegistry().get("ecommerce")))
    assert plan.route_name is None
    assert "quantity" in plan.clarification


def test_comparison_cannot_smuggle_a_write(monkeypatch):
    import pytest
    from fastapi import HTTPException
    class Model:
        async def ainvoke(self, prompt):
            return SimpleNamespace(content='{"route_name":"search_products","parameters":{},"comparison_reads":[{"route_name":"cancel_order","parameters":{"order_id":"o1"}}]}')
    monkeypatch.setattr("app.planner.create_chat_model", lambda: Model())
    with pytest.raises(HTTPException):
        asyncio.run(RoutePlanner().plan(message="compare", application=ApplicationRegistry().get("ecommerce")))


def test_planner_normalizes_common_route_alias(monkeypatch):
    application = ApplicationDefinition(
        app_id="ecommerce",
        name="E-commerce",
        base_url="http://localhost:3333",
        service_key_env="ECOMMERCE_MASTER_CHATBOT_SERVICE_KEY",
        routes=[
            RouteDefinition(
                name="add_cart_item",
                method=HTTPMethod.POST,
                path="/api/v1/cart/items",
                description="Add Cart Item",
                parameters={"variant_id": "Variant ID", "quantity": "Integer quantity"},
                required_parameters=["variant_id", "quantity"],
            )
        ],
    )

    class Model:
        async def ainvoke(self, _):
            return SimpleNamespace(content='{"route_name":"add_to_cart","parameters":{"variant_id":"v1","quantity":1}}')

    monkeypatch.setattr("app.planner.create_chat_model", lambda: Model())
    plan = asyncio.run(RoutePlanner().plan(message="add this", application=application))

    assert plan.route_name == "add_cart_item"
    assert plan.parameters == {"variant_id": "v1", "quantity": 1}


def test_planner_drops_comparison_reads_for_write_primary(monkeypatch):
    application = ApplicationDefinition(
        app_id="ecommerce",
        name="E-commerce",
        base_url="http://localhost:3333",
        service_key_env="ECOMMERCE_MASTER_CHATBOT_SERVICE_KEY",
        routes=[
            RouteDefinition(
                name="add_cart_item",
                method=HTTPMethod.POST,
                path="/api/v1/cart/items",
                description="Add Cart Item",
                parameters={"variant_id": "Variant ID", "quantity": "Integer quantity"},
                required_parameters=["variant_id", "quantity"],
            ),
            RouteDefinition(
                name="products",
                method=HTTPMethod.GET,
                path="/api/v1/products",
                description="Products",
                parameters={"q": "Search query"},
                visibility="public",
                requires_auth=False,
            ),
        ],
    )

    class Model:
        async def ainvoke(self, _):
            return SimpleNamespace(
                content=(
                    '{"route_name":"add_cart_item","parameters":{"variant_id":"v1","quantity":1},'
                    '"comparison_reads":[{"route_name":"products","parameters":{"q":"Classic Industrial"}}]}'
                )
            )

    monkeypatch.setattr("app.planner.create_chat_model", lambda: Model())
    plan = asyncio.run(RoutePlanner().plan(message="add Classic Industrial", application=application))

    assert plan.route_name == "add_cart_item"
    assert plan.comparison_reads == []
