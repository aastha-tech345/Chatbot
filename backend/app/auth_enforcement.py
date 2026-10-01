"""Authentication enforcement layer - validates whether a planned route can be executed with current auth state."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .authorization import AuthState
from .models import ApplicationDefinition, RouteDefinition


@dataclass
class AuthEnforcementResult:
    """Result of authentication enforcement check."""

    allowed: bool
    reason: str | None = None
    error_response: dict[str, Any] | None = None


def enforce_route_authentication(
    route: RouteDefinition,
    application: ApplicationDefinition,
    auth_state: AuthState,
) -> AuthEnforcementResult:
    """Enforce authentication requirements for a route.

    This function validates whether the current auth state satisfies the route's authentication
    requirements. It is called AFTER the route is planned and BEFORE it is executed.

    Args:
        route: The route to be executed
        application: The application owning the route
        auth_state: Current authentication state for the application

    Returns:
        AuthEnforcementResult indicating whether execution is allowed
    """
    # Route is not protected - no auth needed
    if not route.protected:
        return AuthEnforcementResult(allowed=True)

    # Route requires authentication but user is not authenticated
    if not auth_state.authenticated:
        from .authorization import auth_request

        return AuthEnforcementResult(
            allowed=False,
            reason="authentication_required",
            error_response=auth_request(application, expired=auth_state.reason == "expired"),
        )

    # Route requires authentication and user is authenticated for this app - check app_id match
    if auth_state.app_id != application.app_id:
        from .authorization import auth_request

        return AuthEnforcementResult(
            allowed=False,
            reason="wrong_application",
            error_response=auth_request(application),
        )

    # Check role-based access control if route specifies allowed_roles
    if route.allowed_roles and not auth_state.roles.intersection(route.allowed_roles):
        return AuthEnforcementResult(
            allowed=False,
            reason="insufficient_permissions",
            error_response={
                "data": [],
                "execution_error": "Your account does not have permission to use this feature.",
                "intent_category": "AUTH_REQUIRED_ACTION" if route.method != "GET" else "USER_SPECIFIC_QUERY",
            },
        )

    # All checks passed
    return AuthEnforcementResult(allowed=True)


def enforce_plan_authentication(
    planned_routes: list[RouteDefinition],
    application: ApplicationDefinition,
    auth_state: AuthState,
) -> AuthEnforcementResult:
    """Enforce authentication for all routes in a plan (preflight check).

    This validates the entire planned execution before executing any route.

    Args:
        planned_routes: List of routes that will be executed (main + comparison reads)
        application: Application owning the routes
        auth_state: Current authentication state

    Returns:
        AuthEnforcementResult indicating whether the full plan is allowed
    """
    for route in planned_routes:
        result = enforce_route_authentication(route, application, auth_state)
        if not result.allowed:
            return result

    return AuthEnforcementResult(allowed=True)
