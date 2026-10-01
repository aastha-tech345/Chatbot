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
