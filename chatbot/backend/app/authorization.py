"""App-scoped authentication and metadata-driven authorization, independent of the LLM."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx
from fastapi import HTTPException

from .models import ApplicationDefinition, RouteDefinition
from .security import verify_hs256_jwt


@dataclass(frozen=True)
class AuthState:
    app_id: str
    authenticated: bool = False
    user_id: str | None = None
    roles: frozenset[str] = field(default_factory=frozenset)
    reason: str | None = None


async def authenticate(application: ApplicationDefinition, authorization: str | None, verifier=verify_hs256_jwt) -> AuthState:
    if not authorization:
        return AuthState(application.app_id)
    config = application.authentication
    try:
        if config.verification == "introspection":
            if not config.user_info_path:
                return AuthState(application.app_id, reason="unavailable")
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                response = await client.get(application.base_url.rstrip("/") + config.user_info_path, headers={"Authorization": authorization})
            if response.status_code in {401, 403}:
                return AuthState(application.app_id, reason="expired")
            if response.status_code != 200:
                return AuthState(application.app_id, reason="unavailable")
            claims = response.json()
            principal = claims.get(config.principal_field)
            roles = claims.get(config.roles_field, [])
        else:
            claims = verifier(authorization, secret=os.getenv(application.jwt_secret_env, ""), algorithm=application.jwt_algorithm)
            if claims.get("app_id", application.app_id) != application.app_id:
                return AuthState(application.app_id, reason="invalid")
            if config.issuer and claims.get("iss") != config.issuer:
                return AuthState(application.app_id, reason="invalid")
            audiences = claims.get("aud", [])
            if isinstance(audiences, str):
                audiences = [audiences]
            if config.audience and config.audience not in audiences:
                return AuthState(application.app_id, reason="invalid")
            principal = claims.get("sub") or claims.get("user_id") or claims.get("id")
            roles = claims.get("roles", [])
        if not isinstance(principal, (str, int)) or not str(principal):
            return AuthState(application.app_id, reason="invalid")
        safe_roles = frozenset(role for role in roles if isinstance(role, str)) if isinstance(roles, list) else frozenset()
        return AuthState(application.app_id, True, str(principal), safe_roles)
    except HTTPException as exc:
        return AuthState(application.app_id, reason="expired" if exc.status_code == 401 else "unavailable")
    except (httpx.HTTPError, ValueError, AttributeError, TypeError):
        return AuthState(application.app_id, reason="unavailable")


def classify(route: RouteDefinition | None, comparison: bool = False) -> str:
    if route is None:
        return "UNKNOWN"
    if route.protected:
        return "USER_SPECIFIC_QUERY" if route.method == "GET" else "AUTH_REQUIRED_ACTION"
    return "PUBLIC_QUERY" if route.method == "GET" and not comparison else "PUBLIC_ACTION"


def auth_request(application: ApplicationDefinition, *, expired: bool = False) -> dict:
    config = application.authentication.public_config()
    message = ("Your session has expired. Please sign in again to continue." if expired else f"This information or action is linked to your account. Please sign in to {application.name} to continue.")
    if not application.authentication.enabled:
        message = f"This feature requires an authenticated {application.name} account. Sign-in is not configured for this application."
    return {"data": [], "execution_error": message, "auth_required": application.authentication.enabled, "auth_config": config}
