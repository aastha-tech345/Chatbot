import asyncio
import json
import sys

sys.path.insert(0, "chatbot/backend")

from app.app_registry import ApplicationRegistry
from app.authorization import AuthState
from app.models import RoutePlan
from app.workflow import ChatWorkflow


class StubPlanner:
    def __init__(self, plan: RoutePlan) -> None:
        self._plan = plan

    async def plan(self, *, message: str, application):  # noqa: ANN001
        return self._plan


class StubAPIClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def execute(self, *, application, route, parameters, authorization, request_id):  # noqa: ANN001
        self.calls.append(
            {
                "application": application.app_id,
                "route": route.name,
                "parameters": dict(parameters),
                "authorization": authorization,
                "request_id": request_id,
            }
        )
        return self.payload


def _application(tmp_path):
    registry_file = tmp_path / "applications.json"
    registry_file.write_text(
        json.dumps(
            {
                "applications": [
                    {
                        "app_id": "his",
                        "name": "Hospital Information System",
                        "base_url": "http://example.test",
                        "jwt_secret_env": "HIS_JWT_SECRET",
                        "service_key_env": "HIS_SERVICE_KEY",
                        "routes": [
                            {
                                "name": "list_patients",
                                "method": "GET",
                                "path": "/api/v1/patients/",
                                "description": "List patients",
                                "parameters": {},
                            },
                            {
                                "name": "list_appointments",
                                "method": "GET",
                                "path": "/api/v1/appointments/",
                                "description": "List appointments",
                                "parameters": {},
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = ApplicationRegistry(registry_file)
    return registry, registry.get("his")


def test_workflow_returns_real_api_data_for_selected_route(tmp_path) -> None:
    registry, application = _application(tmp_path)
    payload = [
        {"id": "p1", "name": "Alice"},
        {"id": "p2", "name": "Bob"},
    ]
    api_client = StubAPIClient(payload)
    workflow = ChatWorkflow(
        registry,
        StubPlanner(RoutePlan(route_name="list_patients", parameters={})),
        api_client,
    )

    result = asyncio.run(
        workflow.run(
            {
                "application": application,
                "message": "show me all patients",
                "authorization": "Bearer test-token",
                "auth_state": AuthState("his", authenticated=True, user_id="u1"),
                "request_id": "req-1",
            }
        )
    )

    assert api_client.calls[0]["route"] == "list_patients"
    assert result["metadata"]["route"] == "list_patients"
    assert result["data"] == payload
    assert result["response_message"]


def test_workflow_supports_second_selected_route(tmp_path) -> None:
    registry, application = _application(tmp_path)
    payload = [{"id": "a1", "status": "scheduled"}]
    api_client = StubAPIClient(payload)
    workflow = ChatWorkflow(
        registry,
        StubPlanner(RoutePlan(route_name="list_appointments", parameters={})),
        api_client,
    )

    result = asyncio.run(
        workflow.run(
            {
                "application": application,
                "message": "show me all appointments",
                "authorization": "Bearer test-token",
                "auth_state": AuthState("his", authenticated=True, user_id="u1"),
                "request_id": "req-2",
            }
        )
    )

    assert api_client.calls[0]["route"] == "list_appointments"
    assert result["data"] == payload


def test_workflow_returns_clarification_without_api_call(tmp_path) -> None:
    registry, application = _application(tmp_path)
    api_client = StubAPIClient([{"ignored": True}])
    workflow = ChatWorkflow(
        registry,
        StubPlanner(RoutePlan(route_name=None, clarification="Could you clarify what kind of recent updates you need?")),
        api_client,
    )

    result = asyncio.run(
        workflow.run(
            {
                "application": application,
                "message": "show me recent updates",
                "authorization": "Bearer test-token",
                "request_id": "req-3",
            }
        )
    )

    assert api_client.calls == []
    assert result["data"] == []
    assert result["metadata"]["route"] is None
    assert result["response_message"] == "Could you clarify what kind of recent updates you need?"


def test_workflow_supports_conversational_response_without_route(tmp_path) -> None:
    registry, application = _application(tmp_path)
    api_client = StubAPIClient([{"ignored": True}])
    workflow = ChatWorkflow(
        registry,
        StubPlanner(RoutePlan(route_name=None, clarification="I can help with information available in this application. What would you like to know?")),
        api_client,
    )

    result = asyncio.run(
        workflow.run(
            {
                "application": application,
                "message": "hello",
                "authorization": "Bearer test-token",
                "request_id": "req-4",
            }
        )
    )

    assert api_client.calls == []
    assert result["metadata"]["route"] is None
    assert result["response_message"].startswith("I can help")


def test_followup_context_reaches_planner(tmp_path):
    registry, application = _application(tmp_path)
    class ContextPlanner:
        async def plan(self, *, message, application):
            assert 'p1' in message and 'Latest user request: the first one' in message
            return RoutePlan(clarification='Which action?')
    workflow = ChatWorkflow(registry, ContextPlanner(), StubAPIClient([]))
    result = asyncio.run(workflow.run({'application': application, 'message': 'the first one', 'history': [{'data': [{'id': 'p1'}]}], 'authorization': 'Bearer test', 'request_id': 'followup'}))
    assert result['response_message'] == 'Which action?'


def test_comparison_combines_registered_reads(tmp_path):
    from app.models import ReadQuery
    registry, application = _application(tmp_path)
    client = StubAPIClient([{'id': 'record'}])
    workflow = ChatWorkflow(registry, StubPlanner(RoutePlan(route_name='list_patients', comparison_reads=[ReadQuery(route_name='list_appointments')])), client)
    result = asyncio.run(workflow.run({'application': application, 'message': 'compare', 'authorization': 'Bearer test', 'auth_state': AuthState('his', authenticated=True, user_id='u1'), 'request_id': 'compare'}))
    assert len(client.calls) == 2
    assert result['metadata']['presentation'] == 'comparison'
    assert len(result['data']) == 2


def test_business_rejection_is_shown_without_success_message(tmp_path):
    from fastapi import HTTPException
    registry, application = _application(tmp_path)
    class RejectingClient:
        async def execute(self, **kwargs):
            raise HTTPException(status_code=400, detail='This item is already shipped.')
    workflow = ChatWorkflow(registry, StubPlanner(RoutePlan(route_name='list_patients')), RejectingClient())
    result = asyncio.run(workflow.run({'application': application, 'message': 'check', 'authorization': 'Bearer test', 'auth_state': AuthState('his', authenticated=True, user_id='u1'), 'request_id': 'reject'}))
    assert result['data'] == []
    assert result['response_message'] == 'This item is already shipped.'


def test_return_is_blocked_when_openapi_has_no_policy_route(tmp_path):
    registry_file = tmp_path / "applications.json"
    registry_file.write_text(
        json.dumps(
            {
                "applications": [
                    {
                        "app_id": "shop",
                        "name": "Shop",
                        "base_url": "http://shop.test",
                        "jwt_secret_env": "SHOP_JWT",
                        "service_key_env": "SHOP_KEY",
                        "routes": [
                            {
                                "name": "request_return",
                                "method": "POST",
                                "path": "/api/v1/returns",
                                "description": "Create return request",
                                "parameters": {"order_id": "Order ID", "order_item_id": "Order item ID", "reason": "Reason"},
                                "required_parameters": ["order_id", "order_item_id", "reason"],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = ApplicationRegistry(registry_file)
    application = registry.get("shop")
    client = StubAPIClient({"id": "ret-1"})
    workflow = ChatWorkflow(
        registry,
        StubPlanner(RoutePlan(route_name="request_return", parameters={"order_id": "ord-1", "order_item_id": "item-1", "reason": "quality not good"})),
        client,
    )

    result = asyncio.run(
        workflow.run(
            {
                "application": application,
                "message": "product quality not good",
                "authorization": "Bearer test",
                "auth_state": AuthState("shop", authenticated=True, user_id="u1"),
                "request_id": "no-policy-route",
                "history": [
                    {"role": "assistant", "data": json.dumps([{"id": "item-1", "order_id": "ord-1", "status": "delivered", "delivery_date": "2026-09-14T00:00:00+0000"}])}
                ],
            }
        )
    )

    assert client.calls == []
    assert result["data"] == []
    assert "return policy isn't available" in result["response_message"]
    assert result["metadata"]["reason_code"] == "NO_POLICY_CONFIGURED"


def test_return_policy_route_is_called_before_return_endpoint(tmp_path):
    registry_file = tmp_path / "applications.json"
    registry_file.write_text(
        json.dumps(
            {
                "applications": [
                    {
                        "app_id": "shop_policy",
                        "name": "Shop Policy",
                        "base_url": "http://shop.test",
                        "jwt_secret_env": "SHOP_JWT",
                        "service_key_env": "SHOP_KEY",
                        "routes": [
                            {
                                "name": "get_return_policy",
                                "method": "GET",
                                "path": "/api/v1/policies/return",
                                "description": "Get return policy",
                                "parameters": {},
                                "visibility": "private",
                                "requires_auth": True,
                            },
                            {
                                "name": "request_return",
                                "method": "POST",
                                "path": "/api/v1/returns",
                                "description": "Create return request",
                                "parameters": {"order_id": "Order ID", "order_item_id": "Order item ID", "reason": "Reason"},
                                "required_parameters": ["order_id", "order_item_id", "reason"],
                                "visibility": "private",
                                "requires_auth": True,
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = ApplicationRegistry(registry_file)
    application = registry.get("shop_policy")

    class PolicyThenReturnClient(StubAPIClient):
        async def execute(self, *, application, route, parameters, authorization, request_id):
            self.calls.append({"route": route.name, "parameters": dict(parameters)})
            if route.name == "get_return_policy":
                return {
                    "policy_id": "return-v1",
                    "action": "return",
                    "enabled": True,
                    "allowed_statuses": ["delivered"],
                    "window": {"type": "days", "days": 30, "based_on": "delivery_date"},
                }
            return {"id": "ret-1"}

    client = PolicyThenReturnClient({})
    workflow = ChatWorkflow(
        registry,
        StubPlanner(RoutePlan(route_name="request_return", parameters={"order_id": "ord-1", "order_item_id": "item-1", "reason": "quality not good"})),
        client,
    )
    result = asyncio.run(
        workflow.run(
            {
                "application": application,
                "message": "product quality not good",
                "authorization": "Bearer test",
                "auth_state": AuthState("shop_policy", authenticated=True, user_id="u1"),
                "request_id": "policy-first",
                "history": [
                    {"role": "assistant", "data": json.dumps([{"id": "item-1", "order_id": "ord-1", "status": "delivered", "delivery_date": "2026-09-14T00:00:00+0000"}])}
                ],
            }
        )
    )

    assert [call["route"] for call in client.calls] == ["get_return_policy", "request_return"]
    assert result["data"] == [{"id": "ret-1"}]
