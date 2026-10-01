"""
Route planner: selects the correct API route and extracts call parameters.

Token-budget flow
-----------------
1. RouteSelector trims the full route list to a relevant subset that fits within
   the catalog token budget (≤ 2 000 tokens for the catalog section alone).
2. The workflow strips large `data` blobs from conversation history before this
   module is called — history is capped to 1 500 tokens of *text* context.
3. If Groq returns a 413 / token-limit error the planner retries once with an
   even smaller catalog (up to MIN_ROUTES routes) before raising.
"""

from __future__ import annotations

import json
import logging
import re
import asyncio
from string import Formatter
from typing import Sequence

from fastapi import HTTPException, status

from .sanitization import safe_text
from .llm_factory import create_chat_model
from .models import ApplicationDefinition, RouteDefinition, RoutePlan, is_route_available, is_route_disabled
from .route_selector import route_selector, _route_line, MIN_ROUTES

logger = logging.getLogger(__name__)
_RATE_LIMIT_RETRY_DELAYS = (13.0, 26.0)
_ROUTE_ALIASES: dict[str, tuple[str, ...]] = {
    "add_to_cart": ("add_cart_item",),
    "remove_from_cart": ("update_cart_line", "clear_current_cart"),
    "show_cart": ("current_cart",),
    "cart": ("current_cart",),
    "show_products": ("products",),
    "search_products": ("search", "products"),
    "checkout": ("create_stripe_checkout_session",),
    "buy": ("create_stripe_checkout_session",),
    "shipping_addresses": ("my_addresses",),
}

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a planning agent for a shopping assistant. Select the correct API route and extract call parameters.

Return ONLY valid JSON — no markdown, no extra text:
{{"route_name": string|null, "parameters": object, "clarification": string|null, "comparison_reads": [{{"route_name": string, "parameters": object}}]}}

## RULES
- Pick a route only when the request is clear enough to call the API now; otherwise set route_name to null and ask.
- Use only the listed route names and parameter names. Do not invent either.
- Resolve references ("this product", "the second one", "my order") from prior conversation data.
- Never ask the user for internal IDs (product_id, variant_id, cart_item_id, order_id, SKU, UUID) — resolve internally.
- Never ask for passwords.

## PRODUCTS
- For general product browsing ("show products", "show me items") use per_page=10 (default).
- For product name resolution ("add X to cart", "find X") use per_page=20 and q=<name>.
- Never use per_page=100. The UI can only display 10 products at a time.
- Never invent slugs or product IDs.

## CART
- Add: use variant_id from product data; default quantity=1 if unspecified. Never ask for variant_id.
- Remove / update: use variant_id from cart context (GET cart first if needed); quantity=0 removes the item.

## ORDERS
- "Show my orders" / "all orders" → orders list route with NO status filter.
- "Show pending/delivered/cancelled orders" → pass status=<value> only when user explicitly says a status.
- For "last/past N days" order-history requests, pass inclusive start_date and end_date as YYYY-MM-DD values.

## ADDRESS
- Fields: recipient_name, line1, city, state, postal_code. Do NOT ask for address_id.

## CHECKOUT
- Use the Stripe checkout-session route; items=[{{product_id, name, quantity, unit_amount}}].
- Continue an active checkout when the user supplies details or confirms. Use the structured checkout context and its item IDs/prices; do not switch to product browsing.
- Merge supplied details with checkout context parameters. Never discard earlier items, email, or shipping fields.
- Ask only for missing required fields in the chosen route. Shipping and email are optional on the ShopNest Stripe route; do not require payment method, card details, or email unless its schema requires them.
- Never ask the customer for success_path or cancel_path; omit them and let the checkout endpoint use its defaults.
- If clarification is needed, keep route_name and all known parameters and set clarification. Never execute while clarification is set.
- Get customer_email from conversation context; do NOT ask user to retype it.
- Do NOT use the generic /checkout endpoint.

## CANCEL / RETURN
- Cancel without order_id → show orders list first.
- Return/refund without item → show order items with status=delivered.

## COMPARISONS
- Up to 3 GET-only comparison_reads.

## CAPABILITIES
- If a route for the request is not listed, tell the user it is unavailable.

Application: {app_name} (app_id={app_id})
Routes (* = required param):
{catalog}
User request: {message}"""


# ---------------------------------------------------------------------------
# Catalog builder (uses pre-selected routes from RouteSelector)
# ---------------------------------------------------------------------------

def _build_catalog(routes: Sequence[RouteDefinition]) -> str:
    """Build a compact catalog string from an already-selected route list."""
    return "\n".join(_route_line(r) for r in routes)


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 3  # conservative


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class RoutePlanner:
    """LLM planner: selects registered routes and extracts parameters."""

    async def plan(
        self,
        *,
        message: str,
        application: ApplicationDefinition,
        forced_route_names: Sequence[str] | None = None,
    ) -> RoutePlan:
        """
        Plan the next API call.

        Args:
            message:            User message (may include trimmed history prefix).
            application:        Full application definition (all routes available).
            forced_route_names: Route names that must appear in the catalog
                                regardless of relevance score (used on retry).
        """
        # ── 1. Select a relevant, budget-bounded route subset ──────────────
        selected_routes, fallback_used = route_selector.select(
            application,
            message,
            extra_route_names=forced_route_names,
        )

        catalog = _build_catalog(selected_routes)

        prompt = _SYSTEM_PROMPT.format(
            app_name=application.name,
            app_id=application.app_id,
            catalog=catalog,
            message=safe_text(message),
        )

        estimated_tokens = _estimate_tokens(prompt)
        logger.info(
            "[PLANNER] app=%s routes_in_catalog=%d fallback=%s estimated_prompt_tokens=%d",
            application.app_id,
            len(selected_routes),
            fallback_used,
            estimated_tokens,
        )

        # ── 2. Call the LLM ────────────────────────────────────────────────
        model = await create_chat_model()
        try:
            response = await self._invoke_with_rate_limit_retry(
                model,
                prompt,
                application_id=application.app_id,
                route_count=len(selected_routes),
            )
        except Exception as exc:
            # Handle Groq 413 / token-limit errors gracefully
            if _is_token_limit_error(exc):
                logger.warning(
                    "[PLANNER] token_limit_error app=%s estimated_tokens=%d "
                    "retrying with minimal catalog",
                    application.app_id,
                    estimated_tokens,
                )
                return await self._plan_with_minimal_catalog(
                    message=message,
                    application=application,
                    original_error=exc,
                )
            logger.exception(
                "[PLANNER] llm_failed app=%s exc_type=%s message=%s",
                application.app_id,
                type(exc).__name__,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"The planning service failed: {type(exc).__name__}: {exc}",
            ) from exc

        logger.info(
            "[PLANNER] raw_groq_response app=%s response_type=%s content=%s",
            application.app_id,
            type(response).__name__,
            safe_text(str(getattr(response, "content", response)))[:4000],
        )
        plan = self._parse_plan(response.content)
        logger.info(
            "[PLANNER] parsed_route_plan app=%s route_name=%s parameters=%s comparison_reads=%s",
            application.app_id,
            plan.route_name,
            safe_text(json.dumps(plan.parameters, default=str))[:2000],
            safe_text(json.dumps([q.model_dump() for q in plan.comparison_reads], default=str))[:2000],
        )

        # ── 3. Validate and post-process the plan ─────────────────────────
        return self._validate_plan(plan, application, selected_routes)

    async def _invoke_with_rate_limit_retry(
        self,
        model: object,
        prompt: str,
        *,
        application_id: str,
        route_count: int,
    ) -> object:
        attempts = 1 + len(_RATE_LIMIT_RETRY_DELAYS)
        for attempt in range(1, attempts + 1):
            try:
                logger.info(
                    "[PLANNER] groq_request app=%s attempt=%d/%d route_count=%d",
                    application_id,
                    attempt,
                    attempts,
                    route_count,
                )
                response = await model.ainvoke(prompt)  # type: ignore[attr-defined]
                logger.info(
                    "[PLANNER] groq_response_ok app=%s attempt=%d/%d response_type=%s",
                    application_id,
                    attempt,
                    attempts,
                    type(response).__name__,
                )
                return response
            except Exception as exc:
                if not _is_rate_limit_error(exc) or attempt == attempts:
                    logger.exception(
                        "[PLANNER] groq_request_failed app=%s attempt=%d/%d exc_type=%s message=%s",
                        application_id,
                        attempt,
                        attempts,
                        type(exc).__name__,
                        exc,
                    )
                    raise
                delay = _RATE_LIMIT_RETRY_DELAYS[attempt - 1]
                logger.warning(
                    "[PLANNER] groq_rate_limited app=%s attempt=%d/%d retry_after_seconds=%.1f exc_type=%s message=%s",
                    application_id,
                    attempt,
                    attempts,
                    delay,
                    type(exc).__name__,
                    exc,
                )
                await asyncio.sleep(delay)

    async def _plan_with_minimal_catalog(
        self,
        *,
        message: str,
        application: ApplicationDefinition,
        original_error: Exception,
    ) -> RoutePlan:
        """
        Retry with the absolute minimum route set when the first attempt hit the
        token limit.  If this also fails, return a safe clarification response
        instead of propagating a 500 error.
        """
        # Force only the top-MIN_ROUTES scored routes
        selected_routes, _ = route_selector.select(application, message)
        minimal = selected_routes[:MIN_ROUTES]
        catalog = _build_catalog(minimal)

        # Also strip history from the message — keep only the latest user request
        latest_message = _strip_history_prefix(message)

        prompt = _SYSTEM_PROMPT.format(
            app_name=application.name,
            app_id=application.app_id,
            catalog=catalog,
            message=safe_text(latest_message),
        )

        logger.info(
            "[PLANNER] retry app=%s minimal_routes=%d estimated_tokens=%d",
            application.app_id,
            len(minimal),
            _estimate_tokens(prompt),
        )

        model = await create_chat_model()
        try:
            response = await self._invoke_with_rate_limit_retry(
                model,
                prompt,
                application_id=application.app_id,
                route_count=len(minimal),
            )
            logger.info(
                "[PLANNER] raw_groq_response app=%s retry=minimal response_type=%s content=%s",
                application.app_id,
                type(response).__name__,
                safe_text(str(getattr(response, "content", response)))[:4000],
            )
            plan = self._parse_plan(response.content)
            logger.info(
                "[PLANNER] parsed_route_plan app=%s retry=minimal route_name=%s parameters=%s comparison_reads=%s",
                application.app_id,
                plan.route_name,
                safe_text(json.dumps(plan.parameters, default=str))[:2000],
                safe_text(json.dumps([q.model_dump() for q in plan.comparison_reads], default=str))[:2000],
            )
            return self._validate_plan(plan, application, minimal)
        except Exception as retry_exc:
            logger.exception(
                "[PLANNER] retry_failed app=%s original_error_type=%s original_error=%s retry_error_type=%s retry_error=%s",
                application.app_id,
                type(original_error).__name__,
                original_error,
                type(retry_exc).__name__,
                retry_exc,
            )
            # Return a controlled user-facing response instead of a 500
            return RoutePlan(
                clarification=(
                    "I'm having trouble processing your request right now. "
                    "Could you rephrase it more briefly?"
                )
            )

    def _validate_plan(
        self,
        plan: RoutePlan,
        application: ApplicationDefinition,
        visible_routes: Sequence[RouteDefinition],
    ) -> RoutePlan:
        """
        Validate the LLM plan against the full route registry.

        Important: validation uses `application.routes` (the complete list), not
        just the subset shown to the LLM.  This means the plan can reference any
        registered route even if it wasn't in the trimmed catalog.
        """
        logger.info(
            "[PLANNER] validate_plan_start app=%s route_name=%s parameters=%s comparison_reads=%s visible_routes=%d",
            application.app_id,
            plan.route_name,
            safe_text(json.dumps(plan.parameters, default=str))[:2000],
            safe_text(json.dumps([q.model_dump() for q in plan.comparison_reads], default=str))[:2000],
            len(visible_routes),
        )
        # App switch
        if plan.target_app_id and plan.target_app_id != application.app_id:
            if plan.target_app_id not in {app.app_id for app in application.linked_applications}:
                return RoutePlan(
                    clarification="Please open the assistant for the application you want to use."
                )
            return RoutePlan(target_app_id=plan.target_app_id)

        routes_map = {route.name: route for route in application.routes}
        allowed = {route.name: set(route.parameters) for route in application.routes}
        if plan.route_name is not None:
            normalized = _normalize_route_name(plan.route_name, routes_map)
            if normalized != plan.route_name:
                logger.info(
                    "[PLANNER] normalized_route_alias original=%s normalized=%s parameters=%s",
                    plan.route_name,
                    normalized,
                    safe_text(json.dumps(plan.parameters, default=str))[:2000],
                )
                plan.route_name = normalized

        if plan.route_name is not None and plan.route_name not in allowed:
            logger.error(
                "[PLANNER] validate_plan_error route_not_found route='%s' parameters=%s comparison_reads=%s available_count=%d",
                plan.route_name,
                safe_text(json.dumps(plan.parameters, default=str))[:2000],
                safe_text(json.dumps([q.model_dump() for q in plan.comparison_reads], default=str))[:2000],
                len(allowed),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The planner selected an unregistered route.",
            )

        # ── CRITICAL: Check if the selected route is available ────────────
        # This guards against disabled routes slipping through even if they
        # shouldn't have been in the catalog (stale cache, concurrent disable, etc)
        if plan.route_name is not None:
            route = routes_map.get(plan.route_name)
            if route and is_route_disabled(route):
                logger.warning(
                    "[ROUTE_GUARD] planner_selected_disabled_route app=%s route=%s status=%s is_enabled=%s action=blocked",
                    application.app_id, route.name, route.status, route.is_enabled,
                )
                return RoutePlan(
                    clarification="I'm sorry, but I don't currently have access to perform that action."
                )

        # Filter to only declared parameters
        if plan.route_name is not None:
            plan.parameters = {
                key: value
                for key, value in plan.parameters.items()
                if key in allowed[plan.route_name]
            }

        # Check required parameters
        if plan.route_name is not None:
            route = next(r for r in application.routes if r.name == plan.route_name)
            required_path_params = {
                field_name
                for _, field_name, _, _ in Formatter().parse(route.path)
                if field_name
            }
            missing = (required_path_params | set(route.required_parameters)) - {
                key for key, value in plan.parameters.items()
                if value is not None and value != ""
            }
            if missing:
                parameter_names = ", ".join(sorted(missing))
                return RoutePlan(
                    route_name=plan.route_name, parameters=plan.parameters,
                    clarification=f"Please provide the following details: {parameter_names}"
                )

        # Validate comparison reads
        if plan.comparison_reads:
            for query in plan.comparison_reads:
                normalized = _normalize_route_name(query.route_name, routes_map)
                if normalized != query.route_name:
                    logger.info(
                        "[PLANNER] normalized_comparison_route_alias original=%s normalized=%s parameters=%s",
                        query.route_name,
                        normalized,
                        safe_text(json.dumps(query.parameters, default=str))[:2000],
                    )
                    query.route_name = normalized
            # If the LLM set route_name=null but put a valid GET route in
            # comparison_reads (common when it "searches before adding"), promote
            # the first comparison read to the primary route instead of raising 502.
            if plan.route_name is None:
                first_cr = plan.comparison_reads[0]
                cr_route = routes_map.get(first_cr.route_name)
                if cr_route is not None and cr_route.method.value == "GET":
                    logger.info(
                        "[PLANNER] promoting comparison_read '%s' to primary route "
                        "(LLM returned route_name=null with comparison_reads)",
                        first_cr.route_name,
                    )
                    plan.route_name = first_cr.route_name
                    plan.parameters = {
                        k: v for k, v in first_cr.parameters.items()
                        if k in routes_map[first_cr.route_name].parameters
                    }
                    plan.comparison_reads = plan.comparison_reads[1:]
                    # Re-check required parameters for the promoted route
                    promoted_route = cr_route
                    required_path_params = {
                        field_name
                        for _, field_name, _, _ in Formatter().parse(promoted_route.path)
                        if field_name
                    }
                    missing = (required_path_params | set(promoted_route.required_parameters)) - {
                        key for key, value in plan.parameters.items()
                        if value is not None and value != ""
                    }
                    if missing:
                        parameter_names = ", ".join(sorted(missing))
                        return RoutePlan(
                            clarification=f"Please provide the following details: {parameter_names}"
                        )
                    # If no more comparison_reads, we're done
                    if not plan.comparison_reads:
                        return plan
                else:
                    # No valid route to promote — ask for clarification
                    return RoutePlan(
                        clarification="Could you be more specific about what you're looking for?"
                    )

            if routes_map.get(plan.route_name) is None:
                logger.error(
                    "[PLANNER] validate_plan_error comparison_invalid_primary route_name=%s parameters=%s comparison_reads=%s",
                    plan.route_name,
                    safe_text(json.dumps(plan.parameters, default=str))[:2000],
                    safe_text(json.dumps([q.model_dump() for q in plan.comparison_reads], default=str))[:2000],
                )
                raise HTTPException(
                    status_code=502,
                    detail="Comparisons require a valid primary route.",
                )
            if routes_map[plan.route_name].method.value != "GET":
                logger.warning(
                    "[PLANNER] dropping_comparison_reads_for_write route_name=%s parameters=%s comparison_reads=%s method=%s",
                    plan.route_name,
                    safe_text(json.dumps(plan.parameters, default=str))[:2000],
                    safe_text(json.dumps([q.model_dump() for q in plan.comparison_reads], default=str))[:2000],
                    routes_map[plan.route_name].method.value,
                )
                plan.comparison_reads = []
                return plan
            for query in plan.comparison_reads:
                cmp_route = routes_map.get(query.route_name)
                if cmp_route is None or cmp_route.method.value != "GET":
                    logger.error(
                        "[PLANNER] validate_plan_error comparison_read_not_get primary_route=%s comparison_route=%s parameters=%s comparison_reads=%s",
                        plan.route_name,
                        query.route_name,
                        safe_text(json.dumps(plan.parameters, default=str))[:2000],
                        safe_text(json.dumps([q.model_dump() for q in plan.comparison_reads], default=str))[:2000],
                    )
                    raise HTTPException(
                        status_code=502,
                        detail="Comparisons support registered read operations only.",
                    )
                # ── CRITICAL: Check if comparison read route is available
                if cmp_route and is_route_disabled(cmp_route):
                    logger.warning(
                        "[ROUTE_GUARD] planner_comparison_read_disabled app=%s primary_route=%s comparison_route=%s status=%s action=blocked",
                        application.app_id, plan.route_name, cmp_route.name, cmp_route.status,
                    )
                    # Remove disabled comparison read
                    plan.comparison_reads = [q for q in plan.comparison_reads if q.route_name != query.route_name]
                    continue
                query.parameters = {
                    key: value
                    for key, value in query.parameters.items()
                    if key in cmp_route.parameters
                }
                required = (
                    {name for _, name, _, _ in Formatter().parse(cmp_route.path) if name}
                    | set(cmp_route.required_parameters)
                )
                if any(query.parameters.get(key) in (None, "") for key in required):
                    return RoutePlan(
                        clarification="Which products would you like to compare? Please provide their names."
                    )

        logger.info(
            "[PLANNER] validate_plan_ok app=%s route_name=%s parameters=%s comparison_reads=%s",
            application.app_id,
            plan.route_name,
            safe_text(json.dumps(plan.parameters, default=str))[:2000],
            safe_text(json.dumps([q.model_dump() for q in plan.comparison_reads], default=str))[:2000],
        )
        return plan

    def _parse_plan(self, content: object) -> RoutePlan:
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "".join(
                item.get("text", "") for item in content if isinstance(item, dict)
            )
        else:
            text = str(content)

        # Strip markdown code fences if the model wrapped the JSON
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        try:
            return RoutePlan.model_validate(json.loads(text))
        except (TypeError, ValueError) as exc:
            logger.exception(
                "[PLANNER] parse_plan_failed exc_type=%s message=%s raw_content=%s",
                type(exc).__name__,
                exc,
                safe_text(text)[:4000],
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The planner returned an invalid response.",
            ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_token_limit_error(exc: Exception) -> bool:
    """Detect Groq / OpenAI 413 / token-limit errors."""
    msg = str(exc).lower()
    return (
        "413" in msg
        or "request too large" in msg
        or "token" in msg and ("limit" in msg or "exceed" in msg or "quota" in msg)
        or "rate_limit" in msg
        or "context_length_exceeded" in msg
    )


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    return (
        status_code == 429
        or response_status == 429
        or "429" in msg
        or "too many requests" in msg
        or "rate_limit" in msg
    )


def _normalize_route_name(route_name: str, routes_map: dict[str, RouteDefinition]) -> str:
    if route_name in routes_map:
        return route_name
    for candidate in _ROUTE_ALIASES.get(route_name, ()):
        if candidate in routes_map:
            return candidate
    lowered = route_name.lower()
    if lowered in routes_map:
        return lowered
    return route_name


_HISTORY_PREFIX_PATTERN = re.compile(
    r"^Prior conversation \(context only\):\n.*?\nLatest user request:\s*",
    re.DOTALL,
)


def _strip_history_prefix(message: str) -> str:
    """Remove the conversation history prefix, keeping only the latest request."""
    match = _HISTORY_PREFIX_PATTERN.match(message)
    if match:
        return message[match.end():]
    return message
