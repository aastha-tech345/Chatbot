"""
Intelligent route selection — keeps the LLM prompt within the Groq TPM limit.

All 106 routes remain fully available for API execution.
Only the most relevant subset is sent to the LLM for planning.

Architecture:
    User message
        ↓
    RouteSelector.select()
        ↓  (keyword scoring + tag filtering + token budget)
    Small relevant route subset (≤ MAX_CATALOG_ROUTES)
        ↓
    RoutePlanner / LLM
        ↓
    Plan → existing API execution (unchanged)
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from .models import ApplicationDefinition, RouteDefinition, RouteStatus, is_route_available

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Budget constants
# ---------------------------------------------------------------------------

# Approximate chars-per-token ratio (conservative — Groq counts subword tokens)
_CHARS_PER_TOKEN: int = 3

# Hard token budget for the route catalog section of the prompt.
# The full prompt budget is 8 000 TPM (Groq limit).
# Fixed system-prompt instructions ≈ 1 300 tokens.
# History context budget (controlled separately) ≈ 1 500 tokens.
# LLM response ≈ 300 tokens.
# Remaining for catalog: 8 000 - 1 300 - 1 500 - 300 = 4 900 → use 2 000 as a
# conservative catalog cap so the budget never blows up even if history is large.
CATALOG_TOKEN_BUDGET: int = 2_000
CATALOG_CHAR_BUDGET: int = CATALOG_TOKEN_BUDGET * _CHARS_PER_TOKEN  # 6 000 chars

# Minimum routes to always include regardless of budget (avoids empty catalog)
MIN_ROUTES: int = 6

# Maximum routes regardless of budget (safety ceiling)
MAX_ROUTES: int = 20

# ---------------------------------------------------------------------------
# Route groups that are NEVER relevant to normal end-users
# ---------------------------------------------------------------------------

# Prefix patterns — route names starting with these are admin/system routes
_ADMIN_NAME_PREFIXES: tuple[str, ...] = (
    "admin_",
    "seller_",
    "moderate_",
    "settle_",
    "adjust_inventory",
    "update_variant_price",
    "update_order_item_shipping",
    "update_shipping",
    "run_pending_jobs",
    "decision",       # return decision (admin action)
    "stripe_webhook",
    "confirm_stripe_checkout_session",
)

# Exact route names that are internal / system-only
_SYSTEM_ROUTE_NAMES: frozenset[str] = frozenset({
    "healthcheck_health_get",
    "liveness_health_live_get",
    "readiness_health_ready_get",
    "chat",           # ecommerce's own chatbot relay — not for the master chatbot
    "jobs",
    "coupons",        # admin coupon list (different from validate_coupon)
    "create",         # admin coupon create (badly named)
    "summary",        # admin analytics
    "upload_return_proof",
    "register",
    "register_seller",
    "refresh",
})

# ---------------------------------------------------------------------------
# Keyword → route-name/resource mapping for fast pre-selection
# ---------------------------------------------------------------------------
# Each entry: (keyword_pattern, frozenset_of_route_name_fragments)
# If the user message contains the keyword, those route names get a +10 boost.

_KEYWORD_BOOSTS: list[tuple[re.Pattern[str], frozenset[str]]] = [
    (re.compile(r"\b(cart|basket|add.*(to|my).*cart|remove.*cart|bag)\b"), frozenset({
        "cart", "add_cart", "update_cart", "clear_cart",
    })),
    (re.compile(r"\b(order|orders|my order|purchase|bought|track)\b"), frozenset({
        "orders", "order_detail", "order_item", "cancel", "tracking",
    })),
    (re.compile(r"\b(checkout|pay|payment|buy|purchase|stripe)\b"), frozenset({
        "checkout", "stripe", "payment",
    })),
    (re.compile(r"\b(address|addresses|shipping address|delivery address)\b"), frozenset({
        "address",
    })),
    (re.compile(r"\b(return|refund|replace|exchange)\b"), frozenset({
        "return", "refund",
    })),
    (re.compile(r"\b(product|products|item|items|catalog|search|find|show)\b"), frozenset({
        "product", "search", "catalog", "brand", "categor",
    })),
    (re.compile(r"\b(wishlist|wish list|saved|favourites|favorites)\b"), frozenset({
        "wishlist",
    })),
    (re.compile(r"\b(notification|notifications|unread|alert)\b"), frozenset({
        "notification",
    })),
    (re.compile(r"\b(profile|account|me|my account|email|name|update.*profile)\b"), frozenset({
        "me", "profile", "update_me",
    })),
    (re.compile(r"\b(review|reviews|rating|ratings|feedback)\b"), frozenset({
        "review",
    })),
    (re.compile(r"\b(support|ticket|help|complaint|issue)\b"), frozenset({
        "support", "ticket",
    })),
    (re.compile(r"\b(coupon|discount|promo|code|voucher)\b"), frozenset({
        "coupon", "validate_coupon",
    })),
    (re.compile(r"\b(recommend|recommendation|similar|related|suggest)\b"), frozenset({
        "recommendation",
    })),
    (re.compile(r"\b(cancel|cancell)\b"), frozenset({
        "cancel", "orders",
    })),
]


def _is_admin_route(route: RouteDefinition) -> bool:
    """Return True if this route is an admin/system route irrelevant to end-users."""
    name = route.name.lower()
    if name in _SYSTEM_ROUTE_NAMES:
        return True
    for prefix in _ADMIN_NAME_PREFIXES:
        if name.startswith(prefix):
            return True
    return False


def _is_route_enabled(route: RouteDefinition) -> bool:
    """Return True if route is enabled and available for use."""
    return is_route_available(route)
def _keyword_boost(route: RouteDefinition, message_lower: str) -> int:
    """Extra score when user message strongly implies a specific resource group."""
    name = route.name.lower()
    score = 0
    for pattern, fragments in _KEYWORD_BOOSTS:
        if pattern.search(message_lower):
            for frag in fragments:
                if frag in name:
                    score += 10
                    break
    return score


def _word_score(route: RouteDefinition, message_lower: str) -> int:
    """Word-overlap relevance score (existing logic, preserved)."""
    score = 0
    name = route.name.lower()
    desc = (route.description or "").lower()
    words = re.findall(r"\w+", message_lower)
    for word in words:
        if len(word) < 3:
            continue  # skip noise words
        if word in name:
            score += 3
        elif word in desc:
            score += 1
    return score


def _route_line(route: RouteDefinition) -> str:
    """Compact single-line description of a route for the LLM catalog."""
    param_summary = ", ".join(
        f"{k}{'*' if k in route.required_parameters else ''}"
        for k in route.parameters
    ) or "none"
    return (
        f"- {route.name} [{route.method.value}]: {route.description}; "
        f"auth={route.protected}; params={param_summary}"
    )


class RouteSelector:
    """
    Selects a token-budget-aware subset of routes most relevant to a user message.

    All routes remain registered in ApplicationDefinition and are available for
    API execution.  Only the subset returned here is sent to the LLM.
    """

    def select(
        self,
        application: ApplicationDefinition,
        message: str,
        *,
        extra_route_names: Sequence[str] | None = None,
    ) -> tuple[list[RouteDefinition], bool]:
        """
        Return (selected_routes, fallback_used).

        selected_routes  — ordered list of RouteDefinition objects to show the LLM.
        fallback_used    — True when keyword matching failed and a generic set was used.
        """
        all_routes = application.routes
        total = len(all_routes)

        # 1. Remove admin/system routes that are never relevant to end-users
        # 2. Remove disabled routes (they cannot be used by the chatbot)
        customer_routes = [
            r for r in all_routes 
            if not _is_admin_route(r) and _is_route_enabled(r)
        ]

        # 2. Score by keyword + word overlap
        msg_lower = message.lower()
        scored: list[tuple[int, RouteDefinition]] = []
        for route in customer_routes:
            score = _word_score(route, msg_lower) + _keyword_boost(route, msg_lower)
            scored.append((score, route))

        scored.sort(key=lambda x: x[0], reverse=True)

        # 3. Check whether any route has a meaningful score (>0 keyword or word hit)
        has_match = scored and scored[0][0] > 0
        fallback_used = not has_match

        # 4. Always include must-have anchors regardless of score
        #    (auth/me routes are frequently needed for profile/email context)
        anchor_names: frozenset[str] = frozenset({"me", "login"})
        anchor_routes = [r for r in customer_routes if r.name in anchor_names]

        # 5. Force-include any extra route names requested (e.g. from retry logic)
        forced: list[RouteDefinition] = []
        if extra_route_names:
            name_map = {r.name: r for r in all_routes}
            for name in extra_route_names:
                if name in name_map and name_map[name] not in forced:
                    forced.append(name_map[name])

        # 6. Build the selected set within token budget
        selected: list[RouteDefinition] = []
        seen: set[str] = set()
        char_budget = CATALOG_CHAR_BUDGET

        def _add(route: RouteDefinition) -> bool:
            nonlocal char_budget
            if route.name in seen:
                return True
            line = _route_line(route)
            cost = len(line) + 1  # +1 for newline
            if len(selected) >= MAX_ROUTES:
                return False
            if len(selected) >= MIN_ROUTES and cost > char_budget:
                return False
            selected.append(route)
            seen.add(route.name)
            char_budget -= cost
            return True

        # Add forced routes first
        for r in forced:
            _add(r)

        # Add scored routes
        for _score, route in scored:
            if len(selected) >= MAX_ROUTES:
                break
            _add(route)

        # Ensure anchors are present
        for r in anchor_routes:
            _add(r)

        # 7. Fallback: if we got very few routes, add generic shopping essentials
        if len(selected) < MIN_ROUTES:
            fallback_used = True
            _FALLBACK_NAMES = [
                "products", "product_detail", "search",
                "orders", "current_cart", "add_cart_item",
                "create_stripe_checkout_session", "my_addresses",
                "me", "login",
            ]
            name_map = {r.name: r for r in customer_routes if _is_route_enabled(r)}
            for name in _FALLBACK_NAMES:
                if name in name_map:
                    _add(name_map[name])
                if len(selected) >= MIN_ROUTES:
                    break

        n_selected = len(selected)
        estimated_tokens = (CATALOG_CHAR_BUDGET - char_budget) // _CHARS_PER_TOKEN

        logger.info(
            "[ROUTE_SELECTOR] app=%s total_routes=%d customer_routes=%d "
            "selected=%d estimated_catalog_tokens=%d fallback=%s selected_names=%s",
            application.app_id,
            total,
            len(customer_routes),
            n_selected,
            estimated_tokens,
            fallback_used,
            [r.name for r in selected],
        )

        return selected, fallback_used


# Module-level singleton — stateless, safe to share across requests
route_selector = RouteSelector()
