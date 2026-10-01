from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

from fastapi import HTTPException

from langgraph.graph import END, START, StateGraph

from .audit import log_policy_decision
from .auth_enforcement import enforce_plan_authentication
from .checkout_context import update_checkout_context
from .date_filters import parse_order_date_range
from .entity_response import entity_response, entity_summary, records_from
from .authorization import AuthState, auth_request, classify, user_authorization
from .intent_classifier import classify_route, IntentCategory
from .policy_engine import check_action_eligibility
from .models import HTTPMethod
from .policy_models import ActionPolicy, EligibilityChecks, EligibilityResult, PolicyAction, PolicyResolution
from .policy_registry import resolve_policy
from .sanitization import safe_data, safe_text
from .api_client import ApplicationAPIClient
from .app_registry import ApplicationRegistry
from .models import ApplicationDefinition, RouteDefinition, RoutePlan
from .planner import RoutePlanner
from .tool_registry import DynamicToolRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Product response trimming — prevents DOM overload from large payloads
# ---------------------------------------------------------------------------

# Fields kept per product card (enough for UI, not the full schema)
_PRODUCT_CARD_FIELDS = frozenset({
    "id", "name", "slug", "short_description",
    "category_name", "category_slug",
    "brand_name", "brand_slug",
    "average_rating", "review_count",
    "is_published",
    "media",     # trimmed: only first image URL extracted as image_url
    "image",     # common image field
    "image_url", # common image field (underscored)
    "imageUrl",  # common image field (camelCase)
    "thumbnail", # fallback image field
    "thumbnail_url",  # fallback image field
    "product_image",  # fallback image field
    "product_image_url",  # fallback image field
    "variants",  # trimmed: default variant only, minimal fields
})

# Fields kept per variant in the lightweight card
_VARIANT_CARD_FIELDS = frozenset({
    "id", "name", "price", "currency",
    "quantity_available", "is_default",
})

# Hard cap: max products in one chat response (prevents Chrome freeze)
_MAX_PRODUCT_CARDS = 10

# Route names whose payloads are trimmed and capped
_PRODUCT_LIST_ROUTE_NAMES = frozenset({
    "products", "product_detail", "search",
    "recommendations",
})


def _trim_product(product: dict[str, Any]) -> dict[str, Any]:
    """
    Return a lightweight product dict safe for card rendering.

    - Drops `description`, `category_id`, `brand_id`, `is_published`, and all
      other heavy/internal fields not needed in the card UI.
    - Reduces `variants` to the single default (or first) variant with minimal fields.
    - Extracts image from multiple possible image field formats.
    """
    out: dict[str, Any] = {}
    for key in _PRODUCT_CARD_FIELDS:
        if key not in product:
            continue
        if key == "variants":
            variants = product["variants"]
            if isinstance(variants, list):
                default = next(
                    (v for v in variants if isinstance(v, dict) and v.get("is_default")),
                    None,
                )
                if default is None and variants:
                    default = variants[0] if isinstance(variants[0], dict) else None
                if default:
                    out["variants"] = [{k: default[k] for k in _VARIANT_CARD_FIELDS if k in default}]
                else:
                    out["variants"] = []
        elif key == "media":
            # Try to extract first valid image URL from media array
            media = product.get("media")
            if isinstance(media, list) and media:
                first = media[0]
                if isinstance(first, dict):
                    url = first.get("url") or first.get("image_url") or first.get("src")
                    if url:
                        out["image_url"] = url
            # The raw media array is intentionally not forwarded
        elif key in ("image", "image_url", "imageUrl", "thumbnail", "thumbnail_url", "product_image", "product_image_url"):
            # Handle common image field names
            if key not in out:  # Don't override if already extracted
                url = product.get(key)
                if url and isinstance(url, str):
                    out["image_url"] = url
        else:
            out[key] = product[key]
    
    # Try to extract image from common fields if not already found
    if "image_url" not in out:
        for image_field in ["image", "imageUrl", "thumbnail", "thumbnail_url", "product_image", "product_image_url"]:
            if image_field in product:
                url = product[image_field]
                if url and isinstance(url, str):
                    out["image_url"] = url
                    break
    
    return out


# ---------------------------------------------------------------------------
# Policy-gated routes
# ---------------------------------------------------------------------------

_POLICY_GATED_ROUTES: dict[str, PolicyAction] = {
    "cancel_order": "cancel",
    "cancel_my_order": "cancel",
    "request_return": "return",
    "request_refund": "refund",
    "request_replacement": "replacement",
    "request_replace": "replacement",
    "request_exchange": "replacement",
}

_RETURN_REASON_MAP: dict[str, PolicyAction] = {
    "refund": "refund",
    "replacement": "replacement",
}

# ---------------------------------------------------------------------------
# Route-name classification helpers
# ---------------------------------------------------------------------------

# Route name fragments that indicate a Stripe checkout operation
_CHECKOUT_ROUTE_FRAGMENTS = ("stripe", "checkout", "payment_session", "checkout_session")

_ORDER_LIST_ROUTES = {"orders", "list_orders", "my_orders"}
_ORDER_ITEM_ROUTES = {"my_order_items", "list_order_items", "order_items"}
_PRODUCT_ROUTES = {"products", "search_products", "get_product", "list_categories",
                   "product_detail", "brands"}


def _is_checkout_route(route_name: str) -> bool:
    name_lower = route_name.lower()
    return any(frag in name_lower for frag in _CHECKOUT_ROUTE_FRAGMENTS)


def _resolve_action(route_name: str, parameters: dict[str, Any]) -> PolicyAction:
    if "cancel" in route_name.lower():
        return "cancel"
    route_lower = route_name.lower()
    if any(fragment in route_lower for fragment in ("replacement", "replace", "exchange")):
        return "replacement"
    if "refund" in route_lower:
        return "refund"
    reason = str(parameters.get("reason", "")).lower()
    return _RETURN_REASON_MAP.get(reason, "return")


def _is_post_order_action_route(route_name: str) -> bool:
    route_lower = route_name.lower()
    return (
        route_name in _POLICY_GATED_ROUTES
        or any(fragment in route_lower for fragment in ("return", "refund", "replacement", "replace", "exchange"))
    )


def _action_unavailable_message(action: PolicyAction) -> str:
    if action == "replacement":
        return "Sorry, I can't process a replacement because the replacement policy isn't available through the E-commerce system."
    if action == "refund":
        return "Sorry, I can't process a refund because the refund policy isn't available through the E-commerce system."
    return f"Sorry, I can't process a {action} because the {action} policy isn't available through the E-commerce system."


def _select_policy_route(application: ApplicationDefinition, action: PolicyAction) -> RouteDefinition | None:
    action_terms = {
        "replacement": ("replacement", "replace", "exchange"),
        "refund": ("refund",),
        "return": ("return",),
        "cancel": ("cancel", "cancellation"),
    }[action]
    candidates: list[tuple[int, RouteDefinition]] = []
    for route in application.routes:
        if route.method != HTTPMethod.GET:
            continue
        haystack = " ".join(
            [
                route.name,
                route.path,
                route.description,
                *route.parameters.keys(),
                *route.parameters.values(),
            ]
        ).lower()
        if "policy" not in haystack and "policies" not in haystack:
            continue
        score = 1
        if any(term in haystack for term in action_terms):
            score += 10
        if "action" in route.parameters or "type" in route.parameters or "policy_type" in route.parameters:
            score += 3
        candidates.append((score, route))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _policy_route_parameters(route: RouteDefinition, action: PolicyAction) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for name in route.parameters:
        lower = name.lower()
        if lower in {"action", "type", "policy_type", "policy"}:
            params[name] = action
    return params


def _policy_resolution_from_payload(action: PolicyAction, payload: Any) -> PolicyResolution:
    records: list[Any]
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        for key in ("policy", "data"):
            if isinstance(payload.get(key), dict):
                records = [payload[key]]
                break
        else:
            for key in ("policies", "items", "results"):
                if isinstance(payload.get(key), list):
                    records = payload[key]
                    break
            else:
                records = [payload]
    else:
        return PolicyResolution(policy_found=False)

    for record in records:
        if not isinstance(record, dict):
            continue
        raw = dict(record)
        raw_action = str(raw.get("action") or action).lower()
        if raw_action in {"replace", "exchange"}:
            raw_action = "replacement"
        if raw_action != action:
            continue
        raw.setdefault("action", action)
        raw.setdefault("policy_id", f"{action}-policy")
        try:
            policy = ActionPolicy.model_validate(raw)
        except Exception as exc:
            logger.warning("[POLICY] unreadable_policy_payload action=%s error=%s payload=%s", action, exc, safe_data(raw))
            continue
        return PolicyResolution(
            policy_found=True,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            source=policy.scope,
            policy=policy,
        )
    return PolicyResolution(policy_found=False)


# ---------------------------------------------------------------------------
# History slimming — strips large data blobs before sending to LLM
# ---------------------------------------------------------------------------

# Keep only this many chars from each history data blob to preserve
# product/order references ("this product", "the second one") without
# blowing up the Groq token budget.
_HISTORY_DATA_SUMMARY_CHARS = 300


def _slim_history(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Return history turns with large `data` blobs replaced by a short prefix.
    Preserves role/content for conversational context while keeping token cost low.
    """
    slim = []
    for turn in turns:
        entry: dict[str, Any] = {k: v for k, v in turn.items() if k != "data"}
        raw_data = turn.get("data")
        if raw_data:
            if isinstance(raw_data, str):
                summary = raw_data[:_HISTORY_DATA_SUMMARY_CHARS]
                truncated = len(raw_data) > _HISTORY_DATA_SUMMARY_CHARS
            else:
                try:
                    s = json.dumps(raw_data, default=str)
                except Exception:
                    s = str(raw_data)
                summary = s[:_HISTORY_DATA_SUMMARY_CHARS]
                truncated = len(s) > _HISTORY_DATA_SUMMARY_CHARS
            entry["data_summary"] = summary + ("…" if truncated else "")
        slim.append(entry)
    return slim


# ---------------------------------------------------------------------------
# LangGraph state
# ---------------------------------------------------------------------------

class ChatState(TypedDict, total=False):
    application: ApplicationDefinition
    message: str
    auth_state: AuthState
    auth_required: bool
    auth_config: dict[str, Any]
    intent_category: str
    switch_app: dict[str, str]
    request_id: str
    history: list[dict[str, Any]]
    plan: RoutePlan
    data: list[dict[str, Any]]
    entity_response: dict[str, Any]
    checkout_context: dict[str, Any]
    execution_error: str
    response_message: str
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Order context helpers (for policy gate)
# ---------------------------------------------------------------------------

def _extract_order_from_state(state: ChatState, plan: RoutePlan) -> dict[str, Any]:
    params = plan.parameters
    order: dict[str, Any] = {}

    for key in ("order_id", "status", "order_created_at", "payment_date",
                "shipment_date", "delivery_date", "created_at"):
        if params.get(key):
            order[key] = params[key]

    history = state.get("history") or []
    for turn in reversed(history):
        if turn.get("role") == "assistant" and turn.get("data"):
            try:
                data = json.loads(turn["data"]) if isinstance(turn["data"], str) else turn["data"]
                records = data if isinstance(data, list) else [data]
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    oid = params.get("order_id")
                    if oid and str(rec.get("id") or rec.get("order_id")) == str(oid):
                        order = {**rec, **order}
                        break
                    if any(k in rec for k in ("order_created_at", "created_at", "delivery_date")):
                        order = {**rec, **order}
                        break
            except Exception:
                pass
        if order:
            break

    if "order_created_at" not in order and order.get("created_at"):
        order["order_created_at"] = order["created_at"]
    return order


def _extract_order_item_from_state(state: ChatState, plan: RoutePlan) -> dict[str, Any] | None:
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


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

class ChatWorkflow:
    def __init__(
        self,
        registry: ApplicationRegistry,
        planner: RoutePlanner,
        api_client: ApplicationAPIClient,
    ) -> None:
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
        try:
            return await self.graph.ainvoke(state)
        except Exception as exc:
            plan = state.get("plan")
            route_name = getattr(plan, "route_name", None)
            parameters = getattr(plan, "parameters", {})
            logger.exception(
                "[WORKFLOW] unhandled_exception request_id=%s exc_type=%s message=%s route_name=%s parameters=%s",
                state.get("request_id"),
                type(exc).__name__,
                exc,
                route_name,
                safe_text(json.dumps(parameters, default=str))[:2000],
            )
            raise

    async def _plan(self, state: ChatState) -> ChatState:
        message = safe_text(state["message"])
        application = state["application"]

        for candidate in application.routes:
            candidate_path = candidate.path.rstrip("/")
            if candidate.method == HTTPMethod.GET and candidate_path.endswith(("/orders", "/orders/items")):
                sort_fields = (
                    "created_at, order_number, status, product_name"
                    if candidate_path.endswith("/orders/items")
                    else "created_at, status, order_number, total_amount"
                )
                candidate.parameters.update({
                    "status": "Filter by order or item status (pending, confirmed, shipped, delivered, cancelled)",
                    "start_date": "Inclusive order creation date in YYYY-MM-DD format",
                    "end_date": "Inclusive order creation date in YYYY-MM-DD format",
                    "search": "Search order number, product name, or SKU",
                    "sort_by": f"Sort field: {sort_fields}",
                    "sort_order": "Sort direction: asc or desc",
                })
            if candidate.method != HTTPMethod.GET and _is_checkout_route(candidate.name):
                candidate.parameters["chat_checkout"] = "Set true when checkout is started from chat using selected items"
        
        # Log route availability breakdown
        from .models import is_route_available, RouteStatus
        available_routes = [r for r in application.routes if is_route_available(r)]
        disabled_routes = [r for r in application.routes if not is_route_available(r)]
        
        logger.info(
            "[PLAN] app_id=%s routes_total=%d routes_available=%d routes_disabled=%d",
            application.app_id, len(application.routes), len(available_routes), len(disabled_routes)
        )

        context_message = message
        if state.get("history"):
            # Keep last 4 turns but strip heavy data blobs to stay within token budget.
            recent = state["history"][-4:]
            slim = _slim_history(recent)
            context_message = (
                "Prior conversation (context only):\n"
                + json.dumps(slim, default=str)
                + "\nLatest user request: "
                + message
            )

        checkout_context = update_checkout_context(state.get("checkout_context", {}), message, None)
        if checkout_context:
            context_message = ("Structured checkout context (previously supplied facts; do not ask again):\n"
                               + json.dumps(checkout_context, default=str)
                               + "\n" + context_message)

        try:
            plan = await self.planner.plan(message=context_message, application=application)
        except Exception as exc:
            logger.exception(
                "[PLAN] failed app_id=%s request_id=%s exc_type=%s message=%s",
                application.app_id,
                state.get("request_id"),
                type(exc).__name__,
                exc,
            )
            raise
        if plan.route_name:
            order_route = self.registry.route(application, plan.route_name)
            if (
                order_route.method == HTTPMethod.GET
                and order_route.path.rstrip("/").endswith(("/orders", "/orders/items"))
            ):
                date_range = parse_order_date_range(message)
                if date_range:
                    plan.parameters = {
                        **plan.parameters,
                        "start_date": date_range[0],
                        "end_date": date_range[1],
                    }
                normalized_message = message.lower()
                if any(word in normalized_message for word in ("oldest", "earliest", "ascending", "a to z")):
                    plan.parameters.setdefault("sort_order", "asc")
                elif any(word in normalized_message for word in ("newest", "latest", "descending", "z to a")):
                    plan.parameters.setdefault("sort_order", "desc")
                if any(word in normalized_message for word in ("highest amount", "most expensive", "largest total")):
                    plan.parameters.setdefault("sort_by", "total_amount")
                    plan.parameters.setdefault("sort_order", "desc")
                elif any(word in normalized_message for word in ("lowest amount", "least expensive", "smallest total")):
                    plan.parameters.setdefault("sort_by", "total_amount")
                    plan.parameters.setdefault("sort_order", "asc")
        if plan.route_name and _is_checkout_route(plan.route_name):
            checkout_route = self.registry.route(application, plan.route_name)
            checkout_route.parameters.setdefault("chat_checkout", "Chat-originated checkout marker")
            known = checkout_context.get("parameters", {})
            plan.parameters = {**{k: v for k, v in known.items() if k in checkout_route.parameters}, **plan.parameters}
            for stable_field in ("items", "customer_email"):
                if known.get(stable_field) not in (None, "", []):
                    plan.parameters[stable_field] = known[stable_field]
            plan.parameters["chat_checkout"] = True
            missing = [k for k in checkout_route.required_parameters if plan.parameters.get(k) in (None, "", [])]
            if not missing and plan.clarification:
                clarification = plan.clarification.lower()
                requested_fields = {
                    field for field in checkout_route.parameters if field.lower() in clarification
                }
                optional_return_paths = {"success_path", "cancel_path"}
                if requested_fields and requested_fields <= optional_return_paths:
                    plan.clarification = None
                elif plan.clarification.startswith("Please provide the following details:"):
                    plan.clarification = None

        logger.info(
            "[PLAN] complete app_id=%s request_id=%s route_name=%s parameters=%s comparison_reads=%s",
            application.app_id,
            state.get("request_id"),
            plan.route_name,
            safe_text(json.dumps(plan.parameters, default=str))[:2000],
            safe_text(json.dumps([q.model_dump() for q in plan.comparison_reads], default=str))[:2000],
        )
        checkout_context = update_checkout_context(checkout_context, message, plan)
        return {"plan": plan, "checkout_context": checkout_context}

    async def _execute(self, state: ChatState) -> ChatState:
        plan = state["plan"]
        application = state["application"]

        # App switch
        if plan.target_app_id and plan.target_app_id != application.app_id:
            target = next(
                (a for a in application.linked_applications if a.app_id == plan.target_app_id),
                None,
            )
            if target is not None:
                return {"data": [], "switch_app": target.model_dump()}

        if plan.route_name is None or plan.clarification:
            logger.info(
                "[EXECUTE] skipped_no_route request_id=%s clarification=%s",
                state.get("request_id"),
                safe_text(plan.clarification or ""),
            )
            return {"data": [], "intent_category": "UNKNOWN"}

        try:
            route = self.registry.route(application, plan.route_name)
        except Exception as exc:
            logger.exception(
                "[EXECUTE] route_lookup_failed request_id=%s exc_type=%s message=%s route_name=%s parameters=%s",
                state.get("request_id"),
                type(exc).__name__,
                exc,
                plan.route_name,
                safe_text(json.dumps(plan.parameters, default=str))[:2000],
            )
            raise
        
        # ── CRITICAL: Pre-execution route availability check ──────────────
        # Even if the planner approved this route, it might have been disabled
        # after planning (concurrent disable) or the route metadata might be stale.
        from .models import is_route_disabled
        if is_route_disabled(route):
            logger.warning(
                "[ROUTE_GUARD] workflow_route_disabled app=%s route=%s status=%s is_enabled=%s action=blocked request_id=%s",
                application.app_id, route.name, route.status, route.is_enabled, state.get("request_id")
            )
            category = classify(route, bool(plan.comparison_reads))
            return {
                "data": [],
                "execution_error": "I'm sorry, but I don't currently have access to perform that action.",
                "intent_category": category,
            }
        
        auth = state.get("auth_state", AuthState(application.app_id))
        selected = [
            route,
            *[self.registry.route(application, q.route_name) for q in plan.comparison_reads],
        ]

        # Auth preflight
        enforcement = enforce_plan_authentication(selected, application, auth)
        if not enforcement.allowed:
            category = classify(route, bool(plan.comparison_reads))
            result = enforcement.error_response or {"data": [], "execution_error": enforcement.reason}
            return {**result, "intent_category": category}

        category = classify(route, bool(plan.comparison_reads))

        # Policy gate
        if _is_post_order_action_route(plan.route_name):
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
            "[API] app=%s operation=%s method=%s path=%s request_started request_id=%s",
            application.app_id, route.name, route.method.value, route.path, state["request_id"],
        )

        tools = self.tool_registry.build(
            application=application,
            authorization=user_authorization.get(),
            request_id=state["request_id"],
        )

        logger.info(
            "[EXECUTE] route_execution_start request_id=%s route_name=%s parameters=%s comparison_reads=%s",
            state.get("request_id"),
            plan.route_name,
            safe_text(json.dumps(plan.parameters, default=str))[:2000],
            safe_text(json.dumps([q.model_dump() for q in plan.comparison_reads], default=str))[:2000],
        )
        try:
            payload = await tools[route.name].ainvoke(plan.parameters)
        except HTTPException as exc:
            logger.exception(
                "[EXECUTE] route_execution_http_error request_id=%s exc_type=%s status_code=%s message=%s route_name=%s parameters=%s",
                state.get("request_id"),
                type(exc).__name__,
                exc.status_code,
                exc.detail,
                plan.route_name,
                safe_text(json.dumps(plan.parameters, default=str))[:2000],
            )
            if exc.status_code == 401 and route.protected:
                return {**auth_request(application, expired=True), "intent_category": category}
            if exc.status_code in {401, 403}:
                return {
                    "data": [],
                    "execution_error": "The application denied access to this resource.",
                    "intent_category": category,
                }
            if exc.status_code in {400, 404, 409, 422}:
                # CRITICAL: Never expose internal error codes like ROUTE_DISABLED to user
                error_detail = str(exc.detail)
                if error_detail == "ROUTE_DISABLED":
                    error_detail = "Sorry, I'm not able to perform this task right now."
                return {"data": [], "execution_error": error_detail}
            if route.method.value != "GET" and exc.status_code >= 500:
                return {
                    "data": [],
                    "execution_error": f"{type(exc).__name__}: {exc.detail}",
                    "metadata": {
                        "error_type": type(exc).__name__,
                        "status_code": exc.status_code,
                        "route": plan.route_name,
                        "parameters": plan.parameters,
                    },
                }
            raise
        except Exception as exc:
            logger.exception(
                "[EXECUTE] route_execution_unhandled_error request_id=%s exc_type=%s message=%s route_name=%s parameters=%s",
                state.get("request_id"),
                type(exc).__name__,
                exc,
                plan.route_name,
                safe_text(json.dumps(plan.parameters, default=str))[:2000],
            )
            raise

        logger.info(
            "[EXECUTE] route_execution_ok request_id=%s route_name=%s raw_payload_type=%s raw_payload=%s",
            state.get("request_id"),
            plan.route_name,
            type(payload).__name__,
            safe_text(json.dumps(safe_data(payload), default=str))[:4000],
        )
        try:
            data = self._normalize_data(safe_data(payload), route_name=route.name)
        except Exception as exc:
            logger.exception(
                "[NORMALIZE] failed request_id=%s exc_type=%s message=%s route_name=%s parameters=%s raw_payload=%s",
                state.get("request_id"),
                type(exc).__name__,
                exc,
                plan.route_name,
                safe_text(json.dumps(plan.parameters, default=str))[:2000],
                safe_text(json.dumps(safe_data(payload), default=str))[:4000],
            )
            raise
        logger.info(
            "[NORMALIZE] ok request_id=%s route_name=%s records=%d data=%s",
            state.get("request_id"),
            plan.route_name,
            len(data),
            safe_text(json.dumps(data, default=str))[:4000],
        )

        # Comparison reads
        for query in plan.comparison_reads:
            comparison_route = self.registry.route(application, query.route_name)
            try:
                logger.info(
                    "[EXECUTE] comparison_route_start request_id=%s route_name=%s parameters=%s",
                    state.get("request_id"),
                    query.route_name,
                    safe_text(json.dumps(query.parameters, default=str))[:2000],
                )
                c_payload = await tools[query.route_name].ainvoke(query.parameters)
            except HTTPException as exc:
                logger.exception(
                    "[EXECUTE] comparison_route_http_error request_id=%s exc_type=%s status_code=%s message=%s route_name=%s parameters=%s",
                    state.get("request_id"),
                    type(exc).__name__,
                    exc.status_code,
                    exc.detail,
                    query.route_name,
                    safe_text(json.dumps(query.parameters, default=str))[:2000],
                )
                if exc.status_code == 401 and comparison_route.protected:
                    return {**auth_request(application, expired=True), "intent_category": category}
                return {
                    "data": [],
                    "execution_error": "The application could not complete this comparison.",
                    "intent_category": category,
                }
            data.extend(self._normalize_data(safe_data(c_payload), route_name=query.route_name))

        return {"data": data, "intent_category": category,
                "entity_response": entity_response(route, safe_data(payload), state.get("message", "")),
                "checkout_context": update_checkout_context(state.get("checkout_context", {}), state.get("message", ""), plan, data)}

    async def _check_policy(
        self,
        state: ChatState,
        plan: RoutePlan,
        application: ApplicationDefinition,
        auth: AuthState,
    ) -> EligibilityResult | None:
        action = _resolve_action(plan.route_name, plan.parameters)  # type: ignore[arg-type]
        order = _extract_order_from_state(state, plan)
        order_item = _extract_order_item_from_state(state, plan)

        if not order.get("order_created_at") and plan.parameters.get("order_id"):
            try:
                tools = self.tool_registry.build(
                    application=application,
                    authorization=user_authorization.get(),
                    request_id=state["request_id"],
                )
                order_route = next(
                    (r for r in application.routes
                     if "order" in r.name and r.method.value == "GET" and "{order_id}" in r.path),
                    None,
                )
                if order_route and order_route.name in tools:
                    fetched = await tools[order_route.name].ainvoke(
                        {"order_id": plan.parameters["order_id"]}
                    )
                    if isinstance(fetched, dict):
                        fetched_safe = safe_data(fetched)
                        order = {**fetched_safe, **order}
                        if "order_created_at" not in order and order.get("created_at"):
                            order["order_created_at"] = order["created_at"]
            except Exception as exc:
                logger.warning(
                    "[POLICY] failed to fetch order order_id=%s error=%s",
                    plan.parameters.get("order_id"), exc,
                )

        product_id = str(
            (order_item or {}).get("product_id")
            or (order_item or {}).get("slug")
            or ""
        )
        cat = str(
            (order_item or {}).get("category")
            or (order_item or {}).get("category_slug")
            or ""
        )

        resolution = resolve_policy(
            app_id=application.app_id,
            action=action,
            product_id=product_id or None,
            category=cat or None,
        )
        if action in {"return", "refund", "replacement"}:
            resolution = await self._resolve_dynamic_policy(
                state=state,
                application=application,
                action=action,
            )

        try:
            result = check_action_eligibility(
                action=action,
                order=order,
                order_item=order_item,
                resolution=resolution,
                authenticated=auth.authenticated,
            )
            if action in {"return", "refund", "replacement"} and result.reason_code == "NO_POLICY_CONFIGURED":
                result.message = _action_unavailable_message(action)
        except Exception as exc:
            logger.error(
                "[POLICY] engine error action=%s request_id=%s error=%s",
                action, state.get("request_id"), exc,
            )
            from .policy_models import EligibilityChecks
            result = EligibilityResult(
                eligible=False,
                action=action,
                policy_found=resolution.policy_found,
                policy_id=resolution.policy_id,
                policy_version=resolution.policy_version,
                reason_code="POLICY_ENGINE_ERROR",
                message="I couldn't verify the applicable policy for this request.",
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

    async def _resolve_dynamic_policy(
        self,
        *,
        state: ChatState,
        application: ApplicationDefinition,
        action: PolicyAction,
    ) -> PolicyResolution:
        policy_route = _select_policy_route(application, action)
        if policy_route is None:
            logger.info(
                "[POLICY] no_policy_route app_id=%s action=%s request_id=%s",
                application.app_id,
                action,
                state.get("request_id"),
            )
            return PolicyResolution(policy_found=False)

        tools = self.tool_registry.build(
            application=application,
            authorization=user_authorization.get(),
            request_id=state["request_id"],
        )
        try:
            payload = await tools[policy_route.name].ainvoke(_policy_route_parameters(policy_route, action))
        except Exception as exc:
            logger.warning(
                "[POLICY] policy_retrieval_failed app_id=%s action=%s route=%s request_id=%s error=%s",
                application.app_id,
                action,
                policy_route.name,
                state.get("request_id"),
                exc,
            )
            return PolicyResolution(policy_found=False)

        resolution = _policy_resolution_from_payload(action, safe_data(payload))
        if not resolution.policy_found:
            logger.info(
                "[POLICY] policy_not_found app_id=%s action=%s route=%s request_id=%s",
                application.app_id,
                action,
                policy_route.name,
                state.get("request_id"),
            )
        return resolution

    async def _respond(self, state: ChatState) -> ChatState:
        plan = state["plan"]
        base_metadata: dict[str, Any] = {
            "app_id": state["application"].app_id,
            "route": plan.route_name,
            "intent_category": state.get("intent_category", "UNKNOWN"),
        }

        if state.get("switch_app"):
            target = state["switch_app"]
            return {
                "response_message": f"Please switch to {target['name']} for this request.",
                "metadata": {**base_metadata, "switch_app": target},
            }

        if state.get("execution_error"):
            metadata = {
                **base_metadata,
                "outcome": "not_completed",
                "auth_required": state.get("auth_required", False),
            }
            if state.get("auth_config") is not None:
                metadata["authentication"] = state["auth_config"]
            if state.get("metadata"):
                metadata.update({k: v for k, v in state["metadata"].items() if k not in metadata})
            return {"response_message": safe_text(state["execution_error"]), "metadata": metadata}

        if plan.route_name is None or plan.clarification:
            return {
                "response_message": safe_text(plan.clarification or "Please clarify what information you need."),
                "metadata": base_metadata,
            }

        route_name = plan.route_name
        response_data = state.get("data", [])

        metadata: dict[str, Any] = {
            **base_metadata,
            "presentation": "comparison" if plan.comparison_reads else "cards",
            "capabilities": [r.name for r in state["application"].routes],
        }

        # ── Checkout: extract and expose the payment URL ──────────────────
        if _is_checkout_route(route_name) and response_data:
            checkout_url = None
            for item in response_data:
                if isinstance(item, dict):
                    checkout_url = (
                        item.get("checkout_url") or item.get("url") or item.get("session_url")
                    )
                    if checkout_url:
                        break
            if checkout_url:
                metadata["checkout_url"] = checkout_url
                metadata["has_checkout_link"] = True
                metadata["presentation"] = "text"
                return {
                    "response_message": (
                        "Your checkout is ready. Click the link below to complete your payment:\n"
                        + checkout_url
                    ),
                    "metadata": metadata,
                    "data": response_data,
                }

        # ── Flow hints for cancel / return ────────────────────────────────
        message_hint = state.get("message", "").lower()
        if route_name in _ORDER_LIST_ROUTES and any(kw in message_hint for kw in ("cancel", "cancell")):
            metadata["flow"] = "cancel_order"
        elif route_name in _ORDER_ITEM_ROUTES or (
            route_name in _ORDER_LIST_ROUTES
            and any(kw in message_hint for kw in ("return", "refund", "replace"))
        ):
            metadata["flow"] = "return_refund"
        elif route_name in _PRODUCT_ROUTES and not plan.comparison_reads:
            metadata["presentation"] = "cards"

        # ── Product listing: always use cards + expose page metadata ──────
        if route_name in _PRODUCT_LIST_ROUTE_NAMES:
            metadata["presentation"] = "cards"
            metadata["product_page"] = int(plan.parameters.get("page", 1) or 1)
            metadata["product_per_page"] = int(
                plan.parameters.get("per_page", _MAX_PRODUCT_CARDS) or _MAX_PRODUCT_CARDS
            )

        entity = state.get("entity_response")
        if entity and not plan.comparison_reads:
            metadata["entity_response"] = entity
            metadata["entity_type"] = entity["entity_type"]
            response_data = entity["items"]
            summary = entity_summary(entity["entity_type"], len(response_data))
        else:
            summary = self._summarize_data(response_data, route_name)
        return {"response_message": summary, "metadata": metadata, "data": response_data}

    # ------------------------------------------------------------------
    # Data normalization
    # ------------------------------------------------------------------

    def _extract_image_url(self, product: dict[str, Any]) -> str | None:
        """
        Extract image URL from common fields:
        - image, image_url, imageUrl
        - thumbnail, thumbnail_url
        - product_image, product_image_url
        - images (array), media (array), photos
        
        Returns first valid image URL, or None if not found.
        """
        # Single-value image fields
        single_image_fields = [
            "image", "image_url", "imageUrl",
            "thumbnail", "thumbnail_url",
            "product_image", "product_image_url",
        ]
        for field in single_image_fields:
            if field in product:
                url = product[field]
                if isinstance(url, str) and self._is_safe_image_url(url):
                    return url
        
        # Array-based image fields
        array_fields = ["images", "media", "photos"]
        for field in array_fields:
            if field in product and isinstance(product[field], list):
                for item in product[field]:
                    url = None
                    if isinstance(item, str):
                        url = item
                    elif isinstance(item, dict):
                        url = item.get("url") or item.get("image_url") or item.get("src")
                    if url and self._is_safe_image_url(url):
                        return url
        
        return None

    def _is_safe_image_url(self, url: str) -> bool:
        """Validate image URL is safe to render (HTTP/HTTPS only)."""
        if not isinstance(url, str):
            return False
        lower = url.lower()
        # Block unsafe protocols
        if lower.startswith(("javascript:", "data:", "vbscript:")):
            return False
        # Allow http/https only
        if not (lower.startswith("http://") or lower.startswith("https://")):
            return False
        return True

    def _normalize_address_fields(self, records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """
        Normalize diverse address API response formats.
        
        Returns:
            (normalized_records, field_mapping dict)
        
        Maps common address field aliases to standard names:
        - street (address, address_line1, address_line_1, street)
        - city (city, locality)
        - state (state, province, region)
        - postal_code (postal_code, zip_code, zip, pincode)
        - country (country, nation)
        """
        field_aliases = {
            "street": ["address", "address_line1", "address_line_1", "street"],
            "city": ["city", "locality"],
            "state": ["state", "province", "region"],
            "postal_code": ["postal_code", "zip_code", "zip", "pincode"],
            "country": ["country", "nation"],
            "name": ["name", "label", "address_name", "address_label"],
            "phone": ["phone", "mobile", "phone_number"],
            "type": ["type", "label"],
        }
        
        field_mapping = {}
        
        # Determine field mapping from first record if available
        if records:
            first_record = records[0]
            for standard_name, aliases in field_aliases.items():
                for alias in aliases:
                    if alias in first_record:
                        field_mapping[standard_name] = alias
                        break
        
        # Normalize all records using discovered mapping
        normalized = []
        for record in records:
            normalized_record = {}
            for standard_name, alias in field_mapping.items():
                if alias in record:
                    normalized_record[standard_name] = record[alias]
            # Keep unmapped fields as-is (don't drop internal IDs)
            for key, value in record.items():
                if key not in field_mapping.values():
                    normalized_record[key] = value
            normalized.append(normalized_record)
        
        return normalized, field_mapping

    def _detect_data_type(self, records: list[dict[str, Any]]) -> str:
        """
        Detect if response is products, addresses, orders, etc.
        
        Returns data type string for response metadata.
        """
        if not records:
            return "generic_list"
        
        first = records[0]
        keys = set(first.keys()) if isinstance(first, dict) else set()
        
        # Product detection
        if any(k in keys for k in ("product_id", "sku", "brand_name", "brand_id", "average_rating")):
            return "product_list"
        
        # Address detection
        if any(k in keys for k in ("address", "city", "postal_code", "state", "country", "street")):
            return "address_list"
        
        # Order detection
        if any(k in keys for k in ("order_id", "order_number", "total_amount", "order_status")):
            return "order_list"
        
        # Cart detection
        if any(k in keys for k in ("cart_id", "cart_items", "subtotal", "cart_total")):
            return "cart"
        
        return "generic_list"

    def _normalize_data(self, payload: Any, route_name: str = "") -> list[dict[str, Any]]:
        """
        Unwrap API response wrappers ({"items":[...]}, raw list, single object)
        into a flat list of dicts.

        For product listing routes:
        - Trims each product to card-safe fields (no description, no full media array,
          single default variant).
        - Hard-caps at _MAX_PRODUCT_CARDS (10) to prevent browser DOM overload.
        """
        logger.info(
            "[NORMALIZE] start route=%s payload_type=%s payload=%s",
            route_name,
            type(payload).__name__,
            safe_text(json.dumps(payload, default=str))[:4000],
        )
        records = records_from(payload)

        # Trim and cap product listing responses
        if route_name in _PRODUCT_LIST_ROUTE_NAMES and records:
            original_count = len(records)
            records = [_trim_product(r) for r in records[:_MAX_PRODUCT_CARDS]]
            logger.info(
                "[NORMALIZE] product_trim route=%s total=%d returning=%d",
                route_name, original_count, len(records),
            )

        logger.info("[NORMALIZE] finish route=%s records=%d", route_name, len(records))
        return records

    # ------------------------------------------------------------------
    # Response message helper
    # ------------------------------------------------------------------

    def _summarize_data(self, data: list[dict[str, Any]], route_name: str) -> str:
        logger.info("[RESPOND] summarize route=%s records=%d", route_name, len(data))
        if not data:
            if "cart" in route_name:
                return "Your cart is empty."
            if "address" in route_name:
                return "No addresses found."
            return "No results found."
        
        n = len(data)
        
        # Product responses
        if route_name in _PRODUCT_LIST_ROUTE_NAMES:
            return f"Here {'is' if n == 1 else 'are'} {n} product{'s' if n != 1 else ''} for you."
        
        # Cart responses
        if "cart" in route_name:
            return f"Your cart has {n} item{'s' if n != 1 else ''}."
        
        # Address responses
        if "address" in route_name:
            if n == 1:
                return "Found 1 address."
            return f"Found {n} address{'es' if n != 1 else ''}."
        
        # Generic responses
        if n == 1:
            return "Found 1 record."
        return f"Found {n} records."
