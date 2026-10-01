"""Intent classification based on route metadata (not LLM) to determine auth requirements early."""
from __future__ import annotations

from enum import Enum
from typing import NamedTuple

from .models import ApplicationDefinition, RouteDefinition


class IntentCategory(str, Enum):
    """Intent classification categories."""

    PUBLIC_QUERY = "PUBLIC_QUERY"
    USER_SPECIFIC_QUERY = "USER_SPECIFIC_QUERY"
    AUTH_REQUIRED_ACTION = "AUTH_REQUIRED_ACTION"
    PUBLIC_ACTION = "PUBLIC_ACTION"
    UNKNOWN = "UNKNOWN"


class IntentClassification(NamedTuple):
    """Result of intent classification."""

    category: IntentCategory
    requires_auth: bool
    route: RouteDefinition | None = None
    is_comparison: bool = False


def classify_route(route: RouteDefinition | None, is_comparison: bool = False) -> IntentCategory:
    """Classify route intent category based on route metadata.

    This classification is based purely on route definition metadata and does NOT involve the LLM.
    It is used to determine early whether authentication is required before planning.

    Args:
        route: Route definition or None if no route is selected yet
        is_comparison: Whether this is part of a comparison operation

    Returns:
        IntentCategory indicating the classification
    """
    if route is None:
        return IntentCategory.UNKNOWN

    # If route is protected (private, requires_auth, requires_user_context, or has allowed_roles)
    if route.protected:
        # For mutations (POST, PUT, PATCH, DELETE), this is an auth-required action
        if route.method != "GET":
            return IntentCategory.AUTH_REQUIRED_ACTION
        # For GET requests, this is a user-specific query
        return IntentCategory.USER_SPECIFIC_QUERY

    # For public routes
    if route.method == "GET" and not is_comparison:
        return IntentCategory.PUBLIC_QUERY

    # For public mutations or comparisons
    return IntentCategory.PUBLIC_ACTION


def classify_intent(route: RouteDefinition | None, is_comparison: bool = False) -> IntentClassification:
    """Classify intent and determine if authentication is required.

    Args:
        route: Route definition or None
        is_comparison: Whether this is part of a comparison

    Returns:
        IntentClassification with category and auth requirement flag
    """
    category = classify_route(route, is_comparison)
    requires_auth = category in (IntentCategory.USER_SPECIFIC_QUERY, IntentCategory.AUTH_REQUIRED_ACTION)
    return IntentClassification(category=category, requires_auth=requires_auth, route=route, is_comparison=is_comparison)


def would_route_require_auth(application: ApplicationDefinition, route_name: str) -> bool:
    """Check if a specific route in an application requires authentication.

    Useful for validating planned routes before execution.

    Args:
        application: Application definition
        route_name: Name of the route

    Returns:
        True if the route requires authentication
    """
    for route in application.routes:
        if route.name == route_name:
            return route.protected
    return False
