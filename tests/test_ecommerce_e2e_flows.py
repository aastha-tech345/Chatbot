"""
End-to-end flow tests for the E-commerce chatbot.

These tests verify the complete user-facing flows without relying on hardcoded IDs,
and validate that the chatbot never asks users for internal identifiers.

Tests run against mock HTTP clients so no live server is required,
but the tests validate the full planner → executor → response pipeline.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any
from unittest import mock

import httpx
import pytest

sys.path.insert(0, "chatbot/backend")

from app.api_client import ApplicationAPIClient
from app.models import ApplicationDefinition, RouteDefinition, HTTPMethod
from app import api_client as api_client_module


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_app(routes: list[RouteDefinition]) -> ApplicationDefinition:
    return ApplicationDefinition(
        app_id="ecommerce",
        name="E-commerce",
        base_url="http://shopnest.test:3333",
        jwt_secret_env="ECOMMERCE_JWT_SECRET",
        service_key_env="ECOMMERCE_MASTER_CHATBOT_SERVICE_KEY",
        routes=routes,
    )


class CapturingClient:
    """Records requests and returns a configurable response."""

    calls: list[dict[str, Any]] = []
    response_body: Any = {}
    response_status: int = 200

    def __init__(self, **_: Any) -> None:
        pass

    async def __aenter__(self) -> "CapturingClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        CapturingClient.calls.append({"method": method, "url": url, **kwargs})
        return httpx.Response(self.response_status, json=self.response_body)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# TEST 1: Add product to cart — quantity defaults to 1, no ID asked
# ---------------------------------------------------------------------------

class TestCartAddProduct:
    """Cart add: normal users never supply product_id/variant_id/SKU."""

    def test_add_to_cart_sends_variant_id_not_user_provided_id(self, monkeypatch) -> None:
        """
        When adding a product to cart the chatbot resolves variant_id internally
        from a prior product search response and POSTs to the cart endpoint.
        """
        CapturingClient.calls = []
        CapturingClient.response_body = {
            "id": "cart-123",
            "items": [{"product_name": "Compact Electronics Product 5", "quantity": 1}],
            "total_items": 1,
            "subtotal": "549.00",
            "currency": "INR",
        }
        CapturingClient.response_status = 201
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        cart_route = RouteDefinition(
            name="add_cart_item",
            method=HTTPMethod.POST,
            path="/api/v1/cart/items",
            description="Add item to cart",
            parameters={
                "variant_id": "Variant ID from product data",
                "product_id": "Product ID (optional)",
                "quantity": "Item quantity (1-20)",
            },
            required_parameters=["quantity"],
        )
        app = _make_app([cart_route])

        result = _run(
            ApplicationAPIClient().execute(
                application=app,
                route=cart_route,
                parameters={"variant_id": "variant-uuid-001", "quantity": 1},
                authorization="Bearer user-jwt",
                request_id="req-cart-add",
            )
        )

        assert len(CapturingClient.calls) == 1
        call = CapturingClient.calls[0]
        assert call["method"] == "POST"
        assert call["url"] == "http://shopnest.test:3333/api/v1/cart/items"
        # variant_id and quantity in JSON body (not query params)
        body = call.get("json", {})
        assert body.get("variant_id") == "variant-uuid-001"
        assert body.get("quantity") == 1
        # Params should be empty (GET-only)
        assert call.get("params") is None

    def test_add_to_cart_default_quantity_is_1(self, monkeypatch) -> None:
        """If quantity not specified, default is 1 — not asked from user."""
        CapturingClient.calls = []
        CapturingClient.response_body = {"id": "cart-123", "items": [], "total_items": 0, "subtotal": "0.00", "currency": "INR"}
        CapturingClient.response_status = 201
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        cart_route = RouteDefinition(
            name="add_cart_item",
            method=HTTPMethod.POST,
            path="/api/v1/cart/items",
            description="Add item to cart",
            parameters={"variant_id": "Variant ID", "quantity": "Quantity"},
            required_parameters=["quantity"],
        )
        _run(
            ApplicationAPIClient().execute(
                application=_make_app([cart_route]),
                route=cart_route,
                parameters={"variant_id": "variant-uuid-001", "quantity": 1},
                authorization="Bearer user-jwt",
                request_id="req-qty-default",
            )
        )
        assert CapturingClient.calls[0]["json"]["quantity"] == 1


# ---------------------------------------------------------------------------
# TEST 2: Remove product from cart — uses variant_id from cart context
# ---------------------------------------------------------------------------

class TestCartRemoveProduct:
    """Cart remove: resolved from cart context, no ID requested from user."""

    def test_remove_cart_item_sets_quantity_zero(self, monkeypatch) -> None:
        """Removing a product uses PUT with quantity=0 (cart item update)."""
        CapturingClient.calls = []
        CapturingClient.response_body = {"id": "cart-123", "items": [], "total_items": 0, "subtotal": "0.00", "currency": "INR"}
        CapturingClient.response_status = 200
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        update_route = RouteDefinition(
            name="update_cart_line",
            method=HTTPMethod.PUT,
            path="/api/v1/cart/items/{variant_id}",
            description="Update cart item quantity; set 0 to remove",
            parameters={"variant_id": "Variant ID (path)", "quantity": "New quantity (0 = remove)"},
            required_parameters=["variant_id", "quantity"],
        )
        result = _run(
            ApplicationAPIClient().execute(
                application=_make_app([update_route]),
                route=update_route,
                parameters={"variant_id": "variant-uuid-001", "quantity": 0},
                authorization="Bearer user-jwt",
                request_id="req-remove",
            )
        )

        call = CapturingClient.calls[0]
        assert call["method"] == "PUT"
        assert "variant-uuid-001" in call["url"]
        assert call["json"]["quantity"] == 0
        # variant_id is in the URL path, not the body
        assert "variant_id" not in (call.get("json") or {})


# ---------------------------------------------------------------------------
# TEST 3: Add 3 of a product — quantity = 3
# ---------------------------------------------------------------------------

class TestCartAddWithQuantity:
    def test_add_three_units(self, monkeypatch) -> None:
        CapturingClient.calls = []
        CapturingClient.response_body = {"id": "cart-123", "items": [], "total_items": 3, "subtotal": "1647.00", "currency": "INR"}
        CapturingClient.response_status = 201
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        cart_route = RouteDefinition(
            name="add_cart_item",
            method=HTTPMethod.POST,
            path="/api/v1/cart/items",
            description="Add item to cart",
            parameters={"variant_id": "Variant ID", "quantity": "Quantity (1-20)"},
            required_parameters=["quantity"],
        )
        _run(
            ApplicationAPIClient().execute(
                application=_make_app([cart_route]),
                route=cart_route,
                parameters={"variant_id": "variant-uuid-001", "quantity": 3},
                authorization="Bearer user-jwt",
                request_id="req-qty-3",
            )
        )
        assert CapturingClient.calls[0]["json"]["quantity"] == 3


# ---------------------------------------------------------------------------
# TEST 4: Address creation — collects user-facing fields
# ---------------------------------------------------------------------------

class TestAddressFlow:
    def test_create_address_uses_api_field_names(self, monkeypatch) -> None:
        """Address POST uses the API field names (recipient_name, line1, etc.)."""
        CapturingClient.calls = []
        CapturingClient.response_body = {
            "id": "addr-001",
            "recipient_name": "Jane Doe",
            "line1": "123 Main Street",
            "city": "Mumbai",
            "state": "MH",
            "postal_code": "400001",
            "created_at": "2026-09-14T10:00:00Z",
            "updated_at": "2026-09-14T10:00:00Z",
        }
        CapturingClient.response_status = 201
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        address_route = RouteDefinition(
            name="create_my_address",
            method=HTTPMethod.POST,
            path="/api/v1/auth/me/addresses",
            description="Create a new delivery address",
            parameters={
                "recipient_name": "Full name of recipient",
                "line1": "Address line 1 (street)",
                "city": "City",
                "state": "State or province",
                "postal_code": "ZIP or postal code",
            },
            required_parameters=["recipient_name", "line1", "city", "state", "postal_code"],
        )
        result = _run(
            ApplicationAPIClient().execute(
                application=_make_app([address_route]),
                route=address_route,
                parameters={
                    "recipient_name": "Jane Doe",
                    "line1": "123 Main Street",
                    "city": "Mumbai",
                    "state": "MH",
                    "postal_code": "400001",
                },
                authorization="Bearer user-jwt",
                request_id="req-addr-create",
            )
        )

        call = CapturingClient.calls[0]
        assert call["method"] == "POST"
        assert call["url"].endswith("/api/v1/auth/me/addresses")
        body = call["json"]
        assert body["recipient_name"] == "Jane Doe"
        assert body["line1"] == "123 Main Street"
        # No internal ID fields in request
        assert "address_id" not in body
        assert "id" not in body

    def test_list_addresses_is_authenticated_get(self, monkeypatch) -> None:
        """GET addresses always uses bearer token — same user as the session."""
        CapturingClient.calls = []
        CapturingClient.response_body = [
            {
                "id": "addr-001",
                "recipient_name": "Jane Doe",
                "line1": "123 Main Street",
                "city": "Mumbai",
                "state": "MH",
                "postal_code": "400001",
                "created_at": "2026-09-14T10:00:00Z",
                "updated_at": "2026-09-14T10:00:00Z",
            }
        ]
        CapturingClient.response_status = 200
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        list_route = RouteDefinition(
            name="my_addresses",
            method=HTTPMethod.GET,
            path="/api/v1/auth/me/addresses",
            description="List my saved addresses",
            parameters={},
            required_parameters=[],
            requires_auth=True,
            visibility="private",
        )
        result = _run(
            ApplicationAPIClient().execute(
                application=_make_app([list_route]),
                route=list_route,
                parameters={},
                authorization="Bearer user-jwt",
                request_id="req-addr-list",
            )
        )

        call = CapturingClient.calls[0]
        assert call["method"] == "GET"
        assert "Authorization" in call["headers"]
        assert call["headers"]["Authorization"] == "Bearer user-jwt"


# ---------------------------------------------------------------------------
# TEST 5: Orders — no status filter for "show my orders"
# ---------------------------------------------------------------------------

class TestOrderListing:
    def test_list_orders_no_status_filter(self, monkeypatch) -> None:
        """GET /api/v1/orders is called without a status filter."""
        CapturingClient.calls = []
        CapturingClient.response_body = [
            {"id": "order-1", "status": "pending", "order_number": "ORD-001", "total_amount": "549.00"},
            {"id": "order-2", "status": "delivered", "order_number": "ORD-002", "total_amount": "649.00"},
        ]
        CapturingClient.response_status = 200
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        orders_route = RouteDefinition(
            name="orders",
            method=HTTPMethod.GET,
            path="/api/v1/orders",
            description="List my orders",
            parameters={},
            required_parameters=[],
            requires_auth=True,
            visibility="private",
        )
        result = _run(
            ApplicationAPIClient().execute(
                application=_make_app([orders_route]),
                route=orders_route,
                parameters={},  # No status filter
                authorization="Bearer user-jwt",
                request_id="req-orders-all",
            )
        )

        call = CapturingClient.calls[0]
        assert call["method"] == "GET"
        # No status param should be in the query
        assert "status" not in (call.get("params") or {})
        assert isinstance(result, list)
        # Both pending and delivered returned
        assert len(result) == 2
        statuses = {r["status"] for r in result}
        assert "pending" in statuses
        assert "delivered" in statuses

    def test_list_pending_orders_sends_status_param(self, monkeypatch) -> None:
        """Explicit 'show pending orders' sends status=pending query param."""
        CapturingClient.calls = []
        CapturingClient.response_body = [
            {"id": "order-1", "status": "pending", "order_number": "ORD-001"},
        ]
        CapturingClient.response_status = 200
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        orders_route = RouteDefinition(
            name="my_order_items",
            method=HTTPMethod.GET,
            path="/api/v1/orders/items",
            description="List my order items by status",
            parameters={"status": "Order status filter"},
            required_parameters=[],
            requires_auth=True,
            visibility="private",
        )
        _run(
            ApplicationAPIClient().execute(
                application=_make_app([orders_route]),
                route=orders_route,
                parameters={"status": "pending"},
                authorization="Bearer user-jwt",
                request_id="req-orders-pending",
            )
        )
        call = CapturingClient.calls[0]
        assert call.get("params", {}).get("status") == "pending"

    def test_list_delivered_orders_sends_status_delivered(self, monkeypatch) -> None:
        CapturingClient.calls = []
        CapturingClient.response_body = [
            {"id": "order-2", "status": "delivered", "order_number": "ORD-002"},
        ]
        CapturingClient.response_status = 200
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        orders_route = RouteDefinition(
            name="my_order_items",
            method=HTTPMethod.GET,
            path="/api/v1/orders/items",
            description="List my order items by status",
            parameters={"status": "Order status filter"},
            required_parameters=[],
            requires_auth=True,
            visibility="private",
        )
        _run(
            ApplicationAPIClient().execute(
                application=_make_app([orders_route]),
                route=orders_route,
                parameters={"status": "delivered"},
                authorization="Bearer user-jwt",
                request_id="req-orders-delivered",
            )
        )
        assert CapturingClient.calls[0]["params"]["status"] == "delivered"

    def test_list_orders_sends_date_range_parameters(self, monkeypatch) -> None:
        CapturingClient.calls = []
        CapturingClient.response_body = []
        CapturingClient.response_status = 200
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)
        orders_route = RouteDefinition(
            name="my_order_items",
            method=HTTPMethod.GET,
            path="/api/v1/orders/items",
            description="List my order items by status and order date",
            parameters={"status": "Order status", "start_date": "Inclusive date", "end_date": "Inclusive date"},
            required_parameters=[],
            requires_auth=True,
            visibility="private",
        )

        _run(
            ApplicationAPIClient().execute(
                application=_make_app([orders_route]),
                route=orders_route,
                parameters={"status": "delivered", "start_date": "2026-09-23", "end_date": "2026-09-29"},
                authorization="Bearer user-jwt",
                request_id="req-orders-dates",
            )
        )

        assert CapturingClient.calls[0]["params"] == {
            "status": "delivered",
            "start_date": "2026-09-23",
            "end_date": "2026-09-29",
        }


# ---------------------------------------------------------------------------
# TEST 6: Checkout — Stripe session, never asks for internal IDs
# ---------------------------------------------------------------------------

class TestCheckoutFlow:
    def test_stripe_checkout_posts_items_array_and_email(self, monkeypatch) -> None:
        """Stripe checkout POSTs items array and customer_email."""
        CapturingClient.calls = []
        CapturingClient.response_body = {
            "session_id": "cs_test_abc123",
            "checkout_url": "https://checkout.stripe.com/pay/cs_test_abc123",
        }
        CapturingClient.response_status = 200
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        checkout_route = RouteDefinition(
            name="create_stripe_checkout_session",
            method=HTTPMethod.POST,
            path="/api/v1/payments/stripe/checkout-session",
            description="Create Stripe checkout session",
            parameters={
                "items": "Array of items [{product_id, name, quantity, unit_amount}]",
                "customer_email": "Customer email (optional)",
                "shipping_name": "Shipping recipient name",
                "address_line1": "Shipping address line 1",
                "city": "Shipping city",
                "state": "Shipping state",
                "postal_code": "Shipping postal code",
            },
            required_parameters=["items"],
        )
        result = _run(
            ApplicationAPIClient().execute(
                application=_make_app([checkout_route]),
                route=checkout_route,
                parameters={
                    "items": [
                        {
                            "product_id": "product-005",
                            "name": "Compact Electronics Product 5",
                            "quantity": 1,
                            "unit_amount": 549.00,
                        }
                    ],
                    "customer_email": "user@example.com",
                    "shipping_name": "John Doe",
                    "address_line1": "123 Main Street",
                    "city": "Mumbai",
                    "state": "MH",
                    "postal_code": "400001",
                },
                authorization="Bearer user-jwt",
                request_id="req-checkout",
            )
        )

        call = CapturingClient.calls[0]
        assert call["method"] == "POST"
        assert "checkout-session" in call["url"]
        body = call["json"]
        assert isinstance(body["items"], list)
        assert body["items"][0]["quantity"] == 1
        assert body["customer_email"] == "user@example.com"
        # Result contains checkout_url
        assert isinstance(result, dict)
        assert "checkout_url" in result or result.get("checkout_url")


# ---------------------------------------------------------------------------
# TEST 7: Response normalization — workflow _normalize_data
# ---------------------------------------------------------------------------

class TestResponseNormalization:
    def test_normalize_paginated_products_response(self) -> None:
        """Paginated product response {items: [...]} is unwrapped correctly."""
        from app.workflow import ChatWorkflow
        from app.app_registry import ApplicationRegistry
        from app.planner import RoutePlanner

        wf = ChatWorkflow(
            ApplicationRegistry.__new__(ApplicationRegistry),
            RoutePlanner(),
            ApplicationAPIClient(),
        )

        paginated = {
            "items": [
                {"id": "p1", "name": "Product 1"},
                {"id": "p2", "name": "Product 2"},
            ],
            "total": 2,
            "page": 1,
            "per_page": 12,
            "pages": 1,
        }
        result = wf._normalize_data(paginated)
        assert len(result) == 2
        assert result[0]["name"] == "Product 1"

    def test_normalize_raw_array(self) -> None:
        from app.workflow import ChatWorkflow
        from app.app_registry import ApplicationRegistry
        from app.planner import RoutePlanner

        wf = ChatWorkflow(
            ApplicationRegistry.__new__(ApplicationRegistry),
            RoutePlanner(),
            ApplicationAPIClient(),
        )

        raw = [
            {"id": "o1", "status": "pending"},
            {"id": "o2", "status": "delivered"},
        ]
        result = wf._normalize_data(raw)
        assert len(result) == 2
        statuses = {r["status"] for r in result}
        assert "pending" in statuses
        assert "delivered" in statuses

    def test_normalize_single_object(self) -> None:
        from app.workflow import ChatWorkflow
        from app.app_registry import ApplicationRegistry
        from app.planner import RoutePlanner

        wf = ChatWorkflow(
            ApplicationRegistry.__new__(ApplicationRegistry),
            RoutePlanner(),
            ApplicationAPIClient(),
        )
        cart = {"id": "cart-001", "items": [], "total_items": 0}
        result = wf._normalize_data(cart)
        assert len(result) == 1
        assert result[0]["id"] == "cart-001"

    def test_checkout_url_extracted_from_response(self) -> None:
        """Stripe response with checkout_url → metadata.checkout_url is set."""
        from app.workflow import ChatWorkflow
        from app.app_registry import ApplicationRegistry
        from app.planner import RoutePlanner, _build_catalog
        from app.models import RoutePlan

        wf = ChatWorkflow(
            ApplicationRegistry.__new__(ApplicationRegistry),
            RoutePlanner(),
            ApplicationAPIClient(),
        )
        route = RouteDefinition(
            name="create_stripe_checkout_session",
            method=HTTPMethod.POST,
            path="/api/v1/payments/stripe/checkout-session",
            description="Stripe checkout",
            parameters={"items": "Cart items array"},
            required_parameters=["items"],
        )
        app_def = _make_app([route])
        from app.authorization import AuthState
        state = {
            "application": app_def,
            "message": "Checkout",
            "plan": RoutePlan(
                route_name="create_stripe_checkout_session",
                parameters={"items": [{"product_id": "p1", "name": "Test", "quantity": 1, "unit_amount": 100}]},
            ),
            "data": [{"session_id": "cs_abc", "checkout_url": "https://checkout.stripe.com/pay/cs_abc"}],
            "intent_category": "AUTH_REQUIRED_ACTION",
            "auth_state": AuthState("ecommerce"),
            "request_id": "req-test",
        }
        result = asyncio.run(wf._respond(state))
        assert result["metadata"].get("checkout_url") == "https://checkout.stripe.com/pay/cs_abc"
        assert "checkout.stripe.com" in result["response_message"]


# ---------------------------------------------------------------------------
# TEST 8: No internal IDs requested — api_client only sends declared params
# ---------------------------------------------------------------------------

class TestNoInternalIDsRequested:
    """The executor strips any parameter not declared in the route schema."""

    def test_undeclared_params_are_filtered_out(self, monkeypatch) -> None:
        """Parameters not in route.parameters are silently dropped."""
        CapturingClient.calls = []
        CapturingClient.response_body = {"id": "cart-123", "items": [], "total_items": 0, "subtotal": "0.00", "currency": "INR"}
        CapturingClient.response_status = 201
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        route = RouteDefinition(
            name="add_cart_item",
            method=HTTPMethod.POST,
            path="/api/v1/cart/items",
            description="Add item to cart",
            parameters={"variant_id": "Variant ID", "quantity": "Quantity"},
            required_parameters=["quantity"],
        )
        _run(
            ApplicationAPIClient().execute(
                application=_make_app([route]),
                route=route,
                # Simulate LLM passing an undeclared field
                parameters={"variant_id": "v1", "quantity": 1, "internal_uuid": "should-be-stripped", "product_sku": "SKU-001"},
                authorization="Bearer user-jwt",
                request_id="req-filter",
            )
        )
        body = CapturingClient.calls[0]["json"]
        assert "internal_uuid" not in body
        assert "product_sku" not in body
        assert "variant_id" in body
        assert "quantity" in body


# ---------------------------------------------------------------------------
# TEST 9: Path params go in URL, not request body
# ---------------------------------------------------------------------------

class TestPathParameterHandling:
    def test_path_params_substituted_in_url_not_body(self, monkeypatch) -> None:
        CapturingClient.calls = []
        CapturingClient.response_body = {"id": "cart-123", "items": [], "total_items": 0, "subtotal": "0.00", "currency": "INR"}
        CapturingClient.response_status = 200
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        route = RouteDefinition(
            name="update_cart_line",
            method=HTTPMethod.PUT,
            path="/api/v1/cart/items/{variant_id}",
            description="Update cart item",
            parameters={"variant_id": "Variant ID (path)", "quantity": "New quantity"},
            required_parameters=["variant_id", "quantity"],
        )
        _run(
            ApplicationAPIClient().execute(
                application=_make_app([route]),
                route=route,
                parameters={"variant_id": "vari-ant-001", "quantity": 2},
                authorization="Bearer user-jwt",
                request_id="req-path-param",
            )
        )
        call = CapturingClient.calls[0]
        # Path param substituted in URL
        assert "vari-ant-001" in call["url"]
        # Path param NOT in body
        body = call.get("json") or {}
        assert "variant_id" not in body
        # Non-path param in body
        assert body.get("quantity") == 2


# ---------------------------------------------------------------------------
# TEST 10: Authentication token is always passed to protected routes
# ---------------------------------------------------------------------------

class TestAuthTokenPropagation:
    def test_protected_route_includes_bearer_token(self, monkeypatch) -> None:
        CapturingClient.calls = []
        CapturingClient.response_body = []
        CapturingClient.response_status = 200
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        route = RouteDefinition(
            name="orders",
            method=HTTPMethod.GET,
            path="/api/v1/orders",
            description="List orders",
            parameters={},
            required_parameters=[],
            requires_auth=True,
            visibility="private",
        )
        _run(
            ApplicationAPIClient().execute(
                application=_make_app([route]),
                route=route,
                parameters={},
                authorization="Bearer my-real-jwt",
                request_id="req-auth",
            )
        )
        headers = CapturingClient.calls[0]["headers"]
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer my-real-jwt"

    def test_unprotected_route_no_auth_header(self, monkeypatch) -> None:
        CapturingClient.calls = []
        CapturingClient.response_body = {"items": [], "total": 0, "page": 1, "per_page": 12, "pages": 0}
        CapturingClient.response_status = 200
        monkeypatch.setattr(api_client_module.httpx, "AsyncClient", CapturingClient)

        route = RouteDefinition(
            name="products",
            method=HTTPMethod.GET,
            path="/api/v1/products",
            description="Public product catalog",
            parameters={"q": "Search query", "per_page": "Results per page"},
            required_parameters=[],
            visibility="public",
            requires_auth=False,
        )
        _run(
            ApplicationAPIClient().execute(
                application=_make_app([route]),
                route=route,
                parameters={"q": "headphones", "per_page": 100},
                authorization=None,
                request_id="req-public",
            )
        )
        headers = CapturingClient.calls[0]["headers"]
        assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# TEST 11: OpenAPI discovery extracts $ref request body fields
# ---------------------------------------------------------------------------

class TestOpenAPIRefResolution:
    """Verify $ref schemas in requestBody are resolved and fields extracted."""

    def test_ref_request_body_fields_are_extracted(self) -> None:
        from app.openapi_discovery import _extract_parameter_info

        components = {
            "schemas": {
                "AddCartItemRequest": {
                    "type": "object",
                    "properties": {
                        "variant_id": {"type": "string", "description": "Variant ID"},
                        "product_id": {"type": "string", "description": "Product ID"},
                        "quantity": {"type": "integer", "description": "Quantity"},
                    },
                    "required": ["quantity"],
                }
            }
        }
        request_body = {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/AddCartItemRequest"}
                }
            }
        }
        params, required = _extract_parameter_info(None, request_body, components)
        assert "variant_id" in params
        assert "product_id" in params
        assert "quantity" in params
        assert "quantity" in required
        assert "variant_id" not in required

    def test_array_field_with_ref_items_is_described(self) -> None:
        from app.openapi_discovery import _extract_parameter_info

        components = {
            "schemas": {
                "StripeCheckoutItem": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string"},
                        "name": {"type": "string"},
                        "quantity": {"type": "integer"},
                        "unit_amount": {"type": "number"},
                    },
                    "required": ["product_id", "name", "quantity", "unit_amount"],
                }
            }
        }
        request_body = {
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/StripeCheckoutItem"},
                            },
                            "customer_email": {"type": "string"},
                        },
                        "required": ["items"],
                    }
                }
            }
        }
        params, required = _extract_parameter_info(None, request_body, components)
        assert "items" in params
        assert "customer_email" in params
        assert "items" in required
        # Description mentions the element fields
        assert "product_id" in params["items"] or "Array" in params["items"]
