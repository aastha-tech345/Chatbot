from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

from fastapi import HTTPException

from langgraph.graph import END, START, StateGraph

from .audit import log_policy_decision
from .auth_enforcement import enforce_plan_authentication
from .authorization import AuthState, auth_request, classify
from .intent_classifier import classify_route, IntentCategory
from .policy_engine import check_action_eligibility
from .policy_models import EligibilityResult, PolicyAction
from .policy_registry import resolve_policy
from .sanitization import safe_data, safe_text
from .api_client import ApplicationAPIClient
from .app_registry import ApplicationRegistry
from .models import ApplicationDefinition, RoutePlan
from .planner import RoutePlanner
from .tool_registry import DynamicToolRegistry

logger = logging.getLogger(__name__)

# Routes that require a policy gate before executing
_POLICY_GATED_ROUTES: dict[str, PolicyAction] = {
    "cancel_order": "cancel",
    "request_return": "return",   # action is resolved from parameters at runtime
}

# request_return is used for return / refund / replacement — disambiguate by the "reason" param
_RETURN_REASON_MAP: dict[str, PolicyAction] = {
    "refund": "refund",
    "replacement": "replacement",
}


class ChatState(TypedDict, total=False):
    application: ApplicationDefinition
    message: str
    authorization: str | None
    auth_state: AuthState
    auth_required: bool
    auth_config: dict[str, Any]
    intent_category: str
    switch_app: dict[str, str]
    request_id: str
    history: list[dict[str, Any]]
    plan: RoutePlan
    data: list[dict[str, Any]]
    execution_error: str
    response_message: str
    metadata: dict[str, Any]


def _resolve_action(route_name: str, parameters: dict[str, Any]) -> PolicyAction:
    """Determine the PolicyAction from route name + parameters (for request_return)."""
    if route_name == "cancel_order":
        return "cancel"
    reason = str(parameters.get("reason", "")).lower()
    return _RETURN_REASON_MAP.get(reason, "return")


def _extract_order_from_state(state: ChatState, plan: RoutePlan) -> dict[str, Any]:
    """Build a minimal order dict from plan parameters and conversation history."""
    params = plan.parameters
    order: dict[str, Any] = {}

    # Pull direct parameters
    for key in ("order_id", "status", "order_created_at", "payment_date",
                "shipment_date", "delivery_date", "created_at"):
        if params.get(key):
            order[key] = params[key]

    # Enrich from conversation history (last assistant data turn)
    history = state.get("history") or []
    for turn in reversed(history):
        if turn.get("role") == "assistant" and turn.get("data"):
            try:
                data = json.loads(turn["data"]) if isinstance(turn["data"], str) else turn["data"]
                records = data if isinstance(data, list) else [data]
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    # Match by order_id if available
                    oid = params.get("order_id")
                    if oid and str(rec.get("id") or rec.get("order_id")) == str(oid):
                        order = {**rec, **order}  # params take precedence
                        break
                    # Or take first order record found (used for cancel)
                    if any(k in rec for k in ("order_created_at", "created_at", "delivery_date")):
                        order = {**rec, **order}
                        break
            except Exception:
                pass
        if order:
            break

    # Normalise: ShopNest API returns `created_at`; policy engine expects `order_created_at`
    if "order_created_at" not in order and order.get("created_at"):
        order["order_created_at"] = order["created_at"]

    return order


def _extract_order_item_from_state(state: ChatState, plan: RoutePlan) -> dict[str, Any] | None:
    """Extract the order item dict from conversation history using order_item_id."""
    item_id = plan.parameters.get("order_item_id")
    if not item_id:
        return None

    history = state.get("history") or []
    for turn in reversed(history):
        if turn.get("role") == "assistant" and turn.get("data"):
            try:
                data = json.loads(turn["data"]) if isinstance(turn["data"], str) else turn["data"]
                records = data if isinstance(data, list) else [data]
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    rec_id = str(rec.get("id") or rec.get("order_item_id") or "")
                    if rec_id == str(item_id):
                        return rec
            except Exception:
                pass
    return None


class ChatWorkflow:
    def __init__(self, registry: ApplicationRegistry, planner: RoutePlanner, api_client: ApplicationAPIClient) -> None:
        self.registry = registry
        self.planner = planner
        self.api_client = api_client
        self.tool_registry = DynamicToolRegistry(api_client)
        graph = StateGraph(ChatState)
        graph.add_node("plan_query", self._plan)
        graph.add_node("execute_route", self._execute)
        graph.add_node("respond_to_user", self._respond)
        graph.add_edge(START, "plan_query")
        graph.add_edge("plan_query", "execute_route")
        graph.add_edge("execute_route", "respond_to_user")
        graph.add_edge("respond_to_user", END)
        self.graph = graph.compile()

    async def run(self, state: ChatState) -> ChatState:
        return await self.graph.ainvoke(state)

    async def _plan(self, state: ChatState) -> ChatState:
        message = safe_text(state["message"])
        if state.get("history"):
            message = "Prior conversation (context only):\n" + json.dumps(safe_data(state["history"]), default=str) + "\nLatest user request: " + message
        return {"plan": await self.planner.plan(message=message, application=state["application"])}

    async def _execute(self, state: ChatState) -> ChatState:
        plan = state["plan"]
        application = state["application"]
        if plan.target_app_id and plan.target_app_id != application.app_id:
            target = next((app for app in application.linked_applications if app.app_id == plan.target_app_id), None)
            if target is not None:
                return {"data": [], "switch_app": target.model_dump()}
        if plan.route_name is None:
            return {"data": [], "intent_category": "UNKNOWN"}

        route = self.registry.route(application, plan.route_name)
        auth = state.get("auth_state", AuthState(application.app_id))
        selected = [route, *[self.registry.route(application, query.route_name) for query in plan.comparison_reads]]

        # ── Preflight: auth ──────────────────────────────────────────────────
        enforcement = enforce_plan_authentication(selected, application, auth)
        if not enforcement.allowed:
            category = classify(route, bool(plan.comparison_reads))
            result = enforcement.error_response or {"data": [], "execution_error": enforcement.reason}
            return {**result, "intent_category": category}

        category = classify(route, bool(plan.comparison_reads))

        # ── Policy gate (FIRST, before any API call) ─────────────────────────
        if plan.route_name in _POLICY_GATED_ROUTES:
            policy_result = await self._check_policy(state, plan, application, auth)
            if policy_result is not None and not policy_result.eligible:
                return {
                    "data": [],
                    "execution_error": policy_result.message,
                    "intent_category": category,
                    "metadata": {
                        "policy_id": policy_result.policy_id,
                        "policy_version": policy_result.policy_version,
                        "reason_code": policy_result.reason_code,
                        "deadline": policy_result.deadline.isoformat() if policy_result.deadline else None,
                        "policy_checks": policy_result.checks.model_dump(),
                    },
                }

        logger.info(
            "[CHAT] route selected app_id=%s tool=%s target_url=%s method=%s request_id=%s",
            application.app_id,
            route.name,
            f"{application.base_url.rstrip('/')}{route.path}",
            route.method,
            state["request_id"],
        )
        tools = self.tool_registry.build(
            application=application,
            authorization=state.get("authorization"),
            request_id=state["request_id"],
        )
        try:
            payload = await tools[route.name].ainvoke(plan.parameters)
        except HTTPException as exc:
            if exc.status_code == 401 and route.protected:
                return {**auth_request(application, expired=True), "intent_category": category}
            if exc.status_code in {401, 403}:
                return {"data": [], "execution_error": "The application denied access to this resource.", "intent_category": category}
            if exc.status_code in {400, 404, 409, 422}:
                return {"data": [], "execution_error": str(exc.detail)}
            if route.method != "GET" and exc.status_code >= 500:
                return {"data": [], "execution_error": "I couldn't verify whether the change completed. Please check the current status before trying the action again."}
            raise
        data = self._normalize_data(safe_data(payload))
        for query in plan.comparison_reads:
            comparison_route = self.registry.route(application, query.route_name)
            try:
                payload = await tools[query.route_name].ainvoke(query.parameters)
            except HTTPException as exc:
                if exc.status_code == 401 and comparison_route.protected:
                    return {**auth_request(application, expired=True), "intent_category": category}
                return {"data": [], "execution_error": "The application could not complete this comparison.", "intent_category": category}
            data.extend(self._normalize_data(safe_data(payload)))
        return {"data": data, "intent_category": category}

    async def _check_policy(
        self,
        state: ChatState,
        plan: RoutePlan,
        application: ApplicationDefinition,
        auth: AuthState,
    ) -> EligibilityResult | None:
        """Run the policy gate for a gated route. Returns None on unexpected errors (fail-closed)."""
        action = _resolve_action(plan.route_name, plan.parameters)  # type: ignore[arg-type]
        order = _extract_order_from_state(state, plan)
        order_item = _extract_order_item_from_state(state, plan)

        # If order_created_at is still missing, fetch the order from the API directly
        if not order.get("order_created_at") and plan.parameters.get("order_id"):
            try:
                tools = self.tool_registry.build(
                    application=application,
                    authorization=state.get("authorization"),
                    request_id=state["request_id"],
                )
                if "get_order" in tools:
                    fetched = await tools["get_order"].ainvoke({"order_id": plan.parameters["order_id"]})
                    if isinstance(fetched, dict):
                        fetched_safe = safe_data(fetched)
                        order = {**fetched_safe, **order}
                        if "order_created_at" not in order and order.get("created_at"):
                            order["order_created_at"] = order["created_at"]
            except Exception as exc:
                logger.warning("[POLICY] failed to fetch order for policy check order_id=%s error=%s",
                               plan.parameters.get("order_id"), exc)

        product_id = str((order_item or {}).get("product_id") or (order_item or {}).get("slug") or "")
        category = str((order_item or {}).get("category") or (order_item or {}).get("category_slug") or "")

        resolution = resolve_policy(
            app_id=application.app_id,
            action=action,
            product_id=product_id or None,
            category=category or None,
        )

        try:
            result = check_action_eligibility(
                action=action,
                order=order,
                order_item=order_item,
                resolution=resolution,
                authenticated=auth.authenticated,
            )
        except Exception as exc:
            logger.error("[POLICY] engine error action=%s request_id=%s error=%s", action, state.get("request_id"), exc)
            # Fail closed — unknown errors block the action
            from .policy_models import EligibilityChecks
            result = EligibilityResult(
                eligible=False,
                action=action,
                policy_found=resolution.policy_found,
                policy_id=resolution.policy_id,
                policy_version=resolution.policy_version,
                reason_code="POLICY_ENGINE_ERROR",
                message="I couldn't verify the applicable policy for this request, so I can't process it right now.",
                checks=EligibilityChecks(),
            )

        log_policy_decision(
            request_id=state.get("request_id", ""),
            user_id=auth.user_id,
            app_id=application.app_id,
            order_id=str(plan.parameters.get("order_id") or "") or None,
            order_item_id=str(plan.parameters.get("order_item_id") or "") or None,
            action=action,
            result=result,
        )

        return result

    # Routes that indicate a specific interactive flow for the frontend
    _CANCEL_ORDER_ROUTES = {"list_orders"}
    _RETURN_REFUND_ROUTES = {"list_order_items"}
    _PRODUCT_LIST_ROUTES = {"search_products", "get_product", "list_categories"}

    async def _respond(self, state: ChatState) -> ChatState:
        plan = state["plan"]
        metadata = {"app_id": state["application"].app_id, "route": plan.route_name, "intent_category": state.get("intent_category", "UNKNOWN")}
        if state.get("switch_app"):
            target = state["switch_app"]
            return {"response_message": f"Please switch to {target['name']} for this request. Its session is checked separately.", "metadata": {**metadata, "switch_app": target}}
        if state.get("execution_error"):
            metadata.update({"outcome": "not_completed", "auth_required": state.get("auth_required", False)})
            if state.get("auth_config") is not None:
                metadata["authentication"] = state["auth_config"]
            # Carry policy metadata forward if present
            if state.get("metadata"):
                metadata.update({k: v for k, v in state["metadata"].items() if k not in metadata})
            return {"response_message": safe_text(state["execution_error"]), "metadata": metadata}
        if plan.route_name is None:
            return {"response_message": safe_text(plan.clarification or "Please clarify what information you need."), "metadata": metadata}
        metadata.update({"presentation": "comparison" if plan.comparison_reads else "cards", "capabilities": [route.name for route in state["application"].routes]})

        # Attach flow hint so the widget can render the correct interactive UI
        message_hint = state.get("message", "").lower()
        if plan.route_name in self._CANCEL_ORDER_ROUTES and any(kw in message_hint for kw in ("cancel", "cancell")):
            metadata["flow"] = "cancel_order"
        elif plan.route_name in self._RETURN_REFUND_ROUTES or (
            plan.route_name in self._CANCEL_ORDER_ROUTES and any(kw in message_hint for kw in ("return", "refund", "replace"))
        ):
            metadata["flow"] = "return_refund"
        elif plan.route_name in self._PRODUCT_LIST_ROUTES and not plan.comparison_reads:
            metadata["presentation"] = "cards"

        return {"response_message": self._summarize_data(state.get("data", []), plan.route_name), "metadata": metadata}

    def _normalize_data(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            for key in ("items", "data", "results"):
                nested = payload.get(key)
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
            return [payload]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _summarize_data(self, data: list[dict[str, Any]], route_name: str) -> str:
        if not data:
            return f"I completed `{route_name}` but no records were returned."
        if len(data) == 1:
            return f"I completed `{route_name}` and found 1 record."
        return f"I completed `{route_name}` and found {len(data)} records."
