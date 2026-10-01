"""
Tests for RouteSelector and token-budget protection.

Verifies:
- Admin routes are excluded from LLM catalog
- Keyword matching selects the right resource routes
- Token budget is always respected
- Fallback works when no keyword match
- All 106 routes remain registered (available for execution)
- History slim-down reduces token count
- 413 retry path produces a controlled response
"""

from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, "chatbot/backend")

from app.models import ApplicationDefinition, HTTPMethod, RouteDefinition
from app.route_selector import (
    RouteSelector,
    CATALOG_CHAR_BUDGET,
    MAX_ROUTES,
    MIN_ROUTES,
    _is_admin_route,
    _route_line,
)
from app.planner import _estimate_tokens, _SYSTEM_PROMPT, _build_catalog, _strip_history_prefix
from app.workflow import _slim_history


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_route(name: str, method: str = "GET", path: str | None = None, params: dict | None = None, required: list | None = None) -> RouteDefinition:
    return RouteDefinition(
        name=name,
        method=HTTPMethod(method),
        path=path or f"/api/v1/{name.replace('_', '/')}",
        description=f"Route {name}",
        parameters=params or {},
        required_parameters=required or [],
    )


def _make_app(routes: list[RouteDefinition]) -> ApplicationDefinition:
    return ApplicationDefinition(
        app_id="ecommerce",
        name="E-commerce",
        base_url="http://localhost:3333",
        jwt_secret_env="ECOMMERCE_JWT_SECRET",
        service_key_env="ECOMMERCE_MASTER_CHATBOT_SERVICE_KEY",
        routes=routes,
    )


def _ecommerce_routes() -> list[RouteDefinition]:
    """Minimal representative set of the 106 ecommerce routes."""
    return [
        _make_route("products", path="/api/v1/products"),
        _make_route("product_detail", path="/api/v1/products/{slug}", params={"slug": "slug"}, required=["slug"]),
        _make_route("add_cart_item", "POST", "/api/v1/cart/items", {"variant_id": "v", "quantity": "q"}, ["quantity"]),
        _make_route("current_cart", path="/api/v1/cart"),
        _make_route("update_cart_line", "PUT", "/api/v1/cart/items/{variant_id}", {"variant_id": "v", "quantity": "q"}, ["variant_id", "quantity"]),
        _make_route("orders", path="/api/v1/orders"),
        _make_route("order_detail", path="/api/v1/orders/{order_id}", params={"order_id": "id"}, required=["order_id"]),
        _make_route("my_order_items", path="/api/v1/orders/items"),
        _make_route("cancel_my_order", "POST", "/api/v1/orders/{order_id}/cancel", {"order_id": "id"}, ["order_id"]),
        _make_route("create_my_address", "POST", "/api/v1/auth/me/addresses", {"recipient_name": "n", "line1": "l", "city": "c", "state": "s", "postal_code": "p"}, ["recipient_name", "line1", "city", "state", "postal_code"]),
        _make_route("my_addresses", path="/api/v1/auth/me/addresses"),
        _make_route("create_stripe_checkout_session", "POST", "/api/v1/payments/stripe/checkout-session", {"items": "items array", "customer_email": "email"}, ["items"]),
        _make_route("me", path="/api/v1/auth/me"),
        _make_route("login", "POST", "/api/v1/auth/login", {"email": "e", "password": "p"}, ["email", "password"]),
        # Admin routes that should be filtered
        _make_route("admin_list_orders", path="/api/v1/admin/orders"),
        _make_route("admin_products", path="/api/v1/admin/products"),
        _make_route("admin_create_product", "POST", "/api/v1/admin/products"),
        _make_route("seller_products", path="/api/v1/seller/products"),
        _make_route("healthcheck_health_get", path="/health"),
        _make_route("jobs", path="/api/v1/admin/jobs"),
    ]


# ---------------------------------------------------------------------------
# Tests: admin route filtering
# ---------------------------------------------------------------------------

class TestAdminRouteFiltering:
    def test_admin_name_prefix_is_filtered(self):
        route = _make_route("admin_list_orders", path="/api/v1/admin/orders")
        assert _is_admin_route(route) is True

    def test_seller_prefix_is_filtered(self):
        route = _make_route("seller_products", path="/api/v1/seller/products")
        assert _is_admin_route(route) is True

    def test_health_route_is_filtered(self):
        route = _make_route("healthcheck_health_get", path="/health")
        assert _is_admin_route(route) is True

    def test_jobs_system_route_is_filtered(self):
        route = _make_route("jobs", path="/api/v1/admin/jobs")
        assert _is_admin_route(route) is True

    def test_customer_cart_route_not_filtered(self):
        route = _make_route("add_cart_item", "POST", "/api/v1/cart/items")
        assert _is_admin_route(route) is False

    def test_customer_orders_route_not_filtered(self):
        route = _make_route("orders", path="/api/v1/orders")
        assert _is_admin_route(route) is False

    def test_stripe_webhook_is_filtered(self):
        route = _make_route("stripe_webhook", "POST", "/api/v1/payments/stripe/webhook")
        assert _is_admin_route(route) is True

    def test_product_detail_not_filtered(self):
        route = _make_route("product_detail", path="/api/v1/products/{slug}")
        assert _is_admin_route(route) is False


# ---------------------------------------------------------------------------
# Tests: RouteSelector
# ---------------------------------------------------------------------------

class TestRouteSelector:
    def setup_method(self):
        self.selector = RouteSelector()
        self.routes = _ecommerce_routes()
        self.app = _make_app(self.routes)

    def test_admin_routes_never_in_selection(self):
        selected, _ = self.selector.select(self.app, "show admin orders")
        names = {r.name for r in selected}
        assert "admin_list_orders" not in names
        assert "admin_products" not in names
        assert "seller_products" not in names
        assert "healthcheck_health_get" not in names

    def test_cart_keywords_select_cart_routes(self):
        selected, fallback = self.selector.select(self.app, "add product to my cart")
        names = {r.name for r in selected}
        assert "add_cart_item" in names
        assert fallback is False

    def test_order_keywords_select_order_routes(self):
        selected, fallback = self.selector.select(self.app, "show my orders")
        names = {r.name for r in selected}
        assert "orders" in names
        assert fallback is False

    def test_checkout_keywords_select_payment_routes(self):
        selected, _ = self.selector.select(self.app, "I want to checkout and pay")
        names = {r.name for r in selected}
        assert "create_stripe_checkout_session" in names

    def test_address_keywords_select_address_routes(self):
        selected, _ = self.selector.select(self.app, "add my shipping address")
        names = {r.name for r in selected}
        assert "create_my_address" in names or "my_addresses" in names

    def test_vague_message_uses_fallback(self):
        selected, fallback = self.selector.select(self.app, "hello")
        assert len(selected) >= MIN_ROUTES

    def test_max_routes_never_exceeded(self):
        selected, _ = self.selector.select(self.app, "show me everything please")
        assert len(selected) <= MAX_ROUTES

    def test_char_budget_respected(self):
        """Total catalog char length must not exceed the budget."""
        selected, _ = self.selector.select(self.app, "add product to cart checkout pay")
        catalog = "\n".join(_route_line(r) for r in selected)
        assert len(catalog) <= CATALOG_CHAR_BUDGET

    def test_all_routes_still_registered(self):
        """Selecting a subset must not remove routes from the application."""
        total_before = len(self.app.routes)
        self.selector.select(self.app, "show my orders")
        assert len(self.app.routes) == total_before

    def test_forced_route_always_included(self):
        """Routes forced by the caller always appear even if unscored."""
        selected, _ = self.selector.select(
            self.app,
            "hello",
            extra_route_names=["create_stripe_checkout_session"],
        )
        names = {r.name for r in selected}
        assert "create_stripe_checkout_session" in names

    def test_me_anchor_included_for_profile_message(self):
        selected, _ = self.selector.select(self.app, "what is my email")
        names = {r.name for r in selected}
        assert "me" in names


# ---------------------------------------------------------------------------
# Tests: token estimation
# ---------------------------------------------------------------------------

class TestTokenBudget:
    def test_prompt_stays_within_groq_limit(self):
        """Full prompt (system + catalog + typical heavy message) < 6 000 tokens."""
        selector = RouteSelector()
        routes = _ecommerce_routes()
        app = _make_app(routes)

        # Simulate a heavy history context (post slim-down)
        heavy_message = (
            'Prior conversation (context only):\n'
            '[{"role":"user","content":"show products"},{"role":"assistant","content":"Found 20 records.","data_summary":"[{\\"id\\":\\"p1\\",\\"name\\":\\"Product 1\\"}...]"}]\n'
            'Latest user request: I want to checkout with my saved address John Doe 123 Main Street Mumbai MH 400001'
        )

        selected, _ = selector.select(app, heavy_message)
        catalog = _build_catalog(selected)
        prompt = _SYSTEM_PROMPT.format(
            app_name=app.name, app_id=app.app_id,
            catalog=catalog, message=heavy_message,
        )
        tokens = _estimate_tokens(prompt)
        assert tokens < 6_000, f"Prompt too large: {tokens} estimated tokens"

    def test_catalog_char_budget_enforced(self):
        selector = RouteSelector()
        routes = _ecommerce_routes()
        app = _make_app(routes)
        selected, _ = selector.select(app, "add to cart checkout pay order")
        catalog = "\n".join(_route_line(r) for r in selected)
        assert len(catalog) <= CATALOG_CHAR_BUDGET


# ---------------------------------------------------------------------------
# Tests: history slim-down
# ---------------------------------------------------------------------------

class TestSlimHistory:
    def test_data_blob_is_replaced_with_summary(self):
        big_data = json.dumps([{"id": f"p{i}", "name": f"Product {i}", "description": "long text " * 20} for i in range(20)])
        turns = [
            {"role": "user", "content": "show products"},
            {"role": "assistant", "content": "Found 20 records.", "data": big_data},
        ]
        slim = _slim_history(turns)
        assert "data" not in slim[1]
        assert "data_summary" in slim[1]
        assert len(slim[1]["data_summary"]) < len(big_data)

    def test_content_is_preserved(self):
        turns = [
            {"role": "user", "content": "show me orders"},
            {"role": "assistant", "content": "Found 3 orders."},
        ]
        slim = _slim_history(turns)
        assert slim[0]["content"] == "show me orders"
        assert slim[1]["content"] == "Found 3 orders."

    def test_turn_without_data_unchanged(self):
        turns = [{"role": "user", "content": "hello"}]
        slim = _slim_history(turns)
        assert slim[0] == {"role": "user", "content": "hello"}

    def test_slim_reduces_token_count_significantly(self):
        big_data = json.dumps([{"id": f"p{i}", "name": f"Prod {i}", "variants": [{"id": f"v{i}", "price": "500.00"}]} for i in range(20)])
        turns = [
            {"role": "user", "content": "show products"},
            {"role": "assistant", "content": "Found 20.", "data": big_data},
        ]
        raw_chars = len(json.dumps(turns))
        slim = _slim_history(turns)
        slim_chars = len(json.dumps(slim))
        assert slim_chars < raw_chars * 0.3, "Slim should reduce to less than 30% of original"


# ---------------------------------------------------------------------------
# Tests: history prefix stripping
# ---------------------------------------------------------------------------

class TestStripHistoryPrefix:
    def test_strips_prior_conversation_prefix(self):
        msg = "Prior conversation (context only):\n[...history...]\nLatest user request: checkout now"
        result = _strip_history_prefix(msg)
        assert result == "checkout now"

    def test_no_prefix_returns_message_unchanged(self):
        msg = "just a plain message"
        result = _strip_history_prefix(msg)
        assert result == "just a plain message"


# ---------------------------------------------------------------------------
# Tests: 413 / token-limit error handling
# ---------------------------------------------------------------------------

class TestTokenLimitErrorHandling:
    def test_token_limit_error_detected_from_413_message(self):
        from app.planner import _is_token_limit_error
        exc = Exception("Error code: 413 - Request too large for model openai/gpt-oss-20b")
        assert _is_token_limit_error(exc) is True

    def test_token_limit_error_detected_from_context_length(self):
        from app.planner import _is_token_limit_error
        exc = Exception("context_length_exceeded: max 8000 tokens")
        assert _is_token_limit_error(exc) is True

    def test_regular_error_not_detected_as_token_limit(self):
        from app.planner import _is_token_limit_error
        exc = ValueError("some other error")
        assert _is_token_limit_error(exc) is False

    def test_planner_returns_clarification_on_double_413(self, monkeypatch):
        """When both the first and retry attempts hit 413, return a clarification RoutePlan."""
        routes = _ecommerce_routes()
        app = _make_app(routes)

        call_count = 0

        class FakeModel:
            async def ainvoke(self, prompt: str):
                nonlocal call_count
                call_count += 1
                raise Exception("Error code: 413 - Request too large")

        monkeypatch.setattr("app.planner.create_chat_model", lambda: FakeModel())

        from app.planner import RoutePlanner
        plan = asyncio.run(RoutePlanner().plan(message="add product to cart", application=app))

        assert plan.route_name is None
        assert plan.clarification is not None
        assert "rephrase" in plan.clarification.lower() or "trouble" in plan.clarification.lower()
        # Should have tried twice: first attempt + retry
        assert call_count == 2

    def test_planner_succeeds_on_retry_after_413(self, monkeypatch):
        """First call raises 413; retry succeeds with minimal catalog."""
        routes = _ecommerce_routes()
        app = _make_app(routes)

        call_count = 0

        class FakeModel:
            async def ainvoke(self, prompt: str):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("Error code: 413 - Request too large")
                return SimpleNamespace(content='{"route_name": "orders", "parameters": {}, "clarification": null, "comparison_reads": []}')

        monkeypatch.setattr("app.planner.create_chat_model", lambda: FakeModel())

        from app.planner import RoutePlanner
        plan = asyncio.run(RoutePlanner().plan(message="show my orders", application=app))

        assert plan.route_name == "orders"
        assert call_count == 2
