import asyncio
from datetime import date
from types import SimpleNamespace

from app.entity_response import entity_response, records_from
from app.checkout_context import update_checkout_context
from app.date_filters import parse_order_date_range
from app.models import ApplicationDefinition, RouteDefinition, RoutePlan
from app.workflow import ChatWorkflow
from app.app_registry import ApplicationRegistry
from app.authorization import AuthState


def route(path, name="dynamic_operation", method="GET", parameters=None):
    return RouteDefinition(name=name, path=path, method=method, description="Read data", parameters=parameters or {}, requires_auth=False, visibility="public")


def test_all_addresses_preserved():
    addresses = [{"id": str(i), "recipient_name": f"Person {i}", "line1": f"{i} Main Street", "city": "Pune", "postal_code": "411001"} for i in range(12)]
    result = entity_response(route("/api/v1/auth/me/addresses"), addresses)
    assert result["entity_type"] == "address"
    assert result["count"] == 12
    assert result["items"] == addresses


def test_last_seven_days_order_prompt_resolves_inclusive_range():
    assert parse_order_date_range("show me last 7 days orders", today=date(2026, 9, 29)) == (
        "2026-09-23",
        "2026-09-29",
    )


def test_order_list_plan_adds_date_parameters_when_route_metadata_is_stale():
    orders_route = route("/api/v1/orders", name="orders", method="GET")
    app = ApplicationDefinition(app_id="test", name="Test", base_url="http://test", service_key_env="TEST", routes=[orders_route])

    class Planner:
        async def plan(self, **kwargs):
            return RoutePlan(route_name="orders")

    workflow = ChatWorkflow(ApplicationRegistry(), Planner(), SimpleNamespace())
    result = asyncio.run(workflow._plan({"application": app, "message": "show me last 7 days orders"}))

    assert result["plan"].parameters == {"start_date": "2026-09-23", "end_date": "2026-09-29"}
    assert "start_date" in orders_route.parameters


def test_order_items_plan_adds_date_parameters_alongside_status_route():
    items_route = route("/api/v1/orders/items", name="my_order_items", method="GET", parameters={"status": "Order status"})
    app = ApplicationDefinition(app_id="test", name="Test", base_url="http://test", service_key_env="TEST", routes=[items_route])

    class Planner:
        async def plan(self, **kwargs):
            return RoutePlan(route_name="my_order_items", parameters={"status": "delivered"})

    workflow = ChatWorkflow(ApplicationRegistry(), Planner(), SimpleNamespace())
    result = asyncio.run(workflow._plan({"application": app, "message": "show delivered orders from last 7 days"}))

    assert result["plan"].parameters == {
        "status": "delivered",
        "start_date": "2026-09-23",
        "end_date": "2026-09-29",
    }
    assert "end_date" in items_route.parameters


def test_actual_shopnest_cart_shape():
    payload = {"id": "cart", "currency": "INR", "total_items": 2, "subtotal": "1198",
               "items": [{"id": "line", "variant_id": "variant", "product_name": "Headphones", "quantity": 2, "unit_price": "599", "line_total": "1198", "currency": "INR"}]}
    result = entity_response(route("/cart"), payload)
    assert result["entity_type"] == "cart_item"
    assert result["items"][0]["product_name"] == "Headphones"
    assert result["summary"]["subtotal"] == "1198"
    assert records_from({"items": []}) == []


def test_nested_cart_and_other_entities():
    result = entity_response(route("/cart"), {"items": [{"product": {"name": "Shoes"}, "quantity": 3}]})
    assert result["items"][0]["name"] == "Shoes"
    for path, expected in [("/orders", "order"), ("/categories", "category"), ("/brands", "brand"), ("/auth/me", "profile"), ("/products", "product")]:
        assert entity_response(route(path), [{"name": "Example"}])["entity_type"] == expected
    assert entity_response(route("/unusual"), [{"status": "active"}])["items"] == [{"status": "active"}]


def test_checkout_draft_survives_followups():
    products = [{"id": "p1", "name": "Headphones", "brand_name": "Brand", "variants": [{"price": "599", "id": "v1"}]}]
    draft = update_checkout_context({}, "show products", None, products)
    draft = update_checkout_context(draft, "buy first product for me", None)
    assert draft["parameters"]["items"][0]["product_id"] == "p1"
    assert draft["parameters"]["items"][0]["variant_id"] == "v1"
    draft = update_checkout_context(draft, "example@example.test", None)
    plan = RoutePlan(route_name="create_checkout_session", parameters={"shipping_name": "Example", "address_line1": "12 Main Street", "city": "Pune", "state": "MH", "postal_code": "411001"})
    draft = update_checkout_context(draft, "shipping details", plan)
    for _ in range(8):
        draft = update_checkout_context(draft, "yes", None)
    assert draft["parameters"]["items"][0]["unit_amount"] == "599"
    assert draft["parameters"]["customer_email"] == "example@example.test"
    assert draft["parameters"]["postal_code"] == "411001"
    assert update_checkout_context(draft, "cancel checkout", None) == {}


def test_checkout_followup_executes_and_exposes_url():
    checkout = route("/payments/stripe/checkout-session", "create_checkout_session", "POST", {
        "items": "Items",
        "customer_email": "Email",
        "success_path": "Optional success page path",
        "cancel_path": "Optional cancel page path",
    })
    checkout.required_parameters = ["items"]
    app = ApplicationDefinition(app_id="test", name="Test", base_url="http://test", service_key_env="TEST", routes=[checkout])
    draft = {"active": True, "parameters": {"items": [{"product_id": "p1", "variant_id": "v1", "name": "Shoes", "quantity": 1, "unit_amount": "599"}], "customer_email": "example@example.test"}}
    class Planner:
        async def plan(self, *, message, application):
            assert '"product_id": "p1"' in message
            assert '"customer_email": "example@example.test"' in message
            return RoutePlan(route_name=checkout.name, parameters={
                "customer_email": "wrong@example.test",
                "items": [{"product_id": "bad", "name": "Invalid", "quantity": 1, "unit_amount": "0"}],
            },
                             clarification="Please provide success_path and cancel_path for the checkout.")
    class Client:
        async def execute(self, **kwargs):
            assert kwargs["parameters"] == {**draft["parameters"], "chat_checkout": True}
            return {"data": {"checkout_url": "https://checkout.example.test/session", "session_id": "session"}}
    workflow = ChatWorkflow(ApplicationRegistry(), Planner(), Client())
    result = asyncio.run(workflow.run({"application": app, "message": "yes", "request_id": "checkout-test", "checkout_context": draft, "auth_state": AuthState("test")}))
    assert result["response_message"].startswith("Your checkout is ready.")
    assert result["metadata"]["checkout_url"] == "https://checkout.example.test/session"


def test_partial_checkout_never_executes():
    checkout = route("/checkout", "checkout", "POST")
    app = ApplicationDefinition(app_id="test", name="Test", base_url="http://test", service_key_env="TEST", routes=[checkout])
    class Planner:
        async def plan(self, **kwargs):
            return RoutePlan(route_name="checkout", parameters={}, clarification="Which product?")
    class Client:
        async def execute(self, **kwargs):
            raise AssertionError("Partial checkout must not execute")
    workflow = ChatWorkflow(ApplicationRegistry(), Planner(), Client())
    result = asyncio.run(workflow.run({"application": app, "message": "buy", "request_id": "partial"}))
    assert result["response_message"] == "Which product?"
