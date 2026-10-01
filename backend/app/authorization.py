"""App-scoped authentication and metadata-driven authorization, independent of the LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from contextvars import ContextVar

import httpx
from fastapi import HTTPException

from .models import ApplicationDefinition, RouteDefinition
from .security import verify_hs256_jwt


# Execution-only context; never included in graph state or tool arguments.
user_authorization: ContextVar[str | None] = ContextVar("user_authorization", default=None)


def normalize_authorization(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    value = value.strip()
    if value.lower().startswith("bearer "):
        return value
    return f"Bearer {value}"


def service_headers(application: ApplicationDefinition) -> dict[str, str]:
    from .app_registry import application_registry
    key = application_registry.get_service_key(application.app_id)
    return {"X-Master-Chatbot-Service-Key": key} if key else {}


@dataclass(frozen=True)
class AuthState:
    app_id: str
    authenticated: bool = False
    user_id: str | None = None
    roles: frozenset[str] = field(default_factory=frozenset)
    reason: str | None = None


async def authenticate(application: ApplicationDefinition, authorization: str | None, verifier=verify_hs256_jwt) -> AuthState:
    authorization = normalize_authorization(authorization)
    if not authorization:
        return AuthState(application.app_id)
    config = application.authentication
    try:
        if config.verification == "introspection":
            if not config.user_info_path:
                return AuthState(application.app_id, reason="unavailable")
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                response = await client.get(application.base_url.rstrip("/") + config.user_info_path, headers={**service_headers(application), "Authorization": authorization})
            if response.status_code in {401, 403}:
                return AuthState(application.app_id, reason="expired")
            if response.status_code != 200:
                return AuthState(application.app_id, reason="unavailable")
            claims = response.json()
            principal = claims.get(config.principal_field)
            roles = claims.get(config.roles_field, [])
        else:
            # Resolve JWT secret from DB via application_registry
            jwt_secret = _get_jwt_secret(application)
            claims = verifier(authorization, secret=jwt_secret, algorithm=application.jwt_algorithm)
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


def _get_jwt_secret(application: ApplicationDefinition) -> str:
    """
    Resolve the JWT secret for an application.
    Prefers the DB registry (sentinel env name pattern: __db__<app_id>__jwt_secret__).
    Falls back to os.getenv() for backward compatibility during migration.
    """
    jwt_secret_env = application.jwt_secret_env or ""

    # DB-backed sentinel value
    if jwt_secret_env.startswith("__db__") and jwt_secret_env.endswith("__jwt_secret__"):
        try:
            from .app_registry import application_registry
            return application_registry.get_jwt_secret(application.app_id)
        except Exception:
            return ""

    # Legacy fallback: read from environment (only during migration period)
    import os
    return os.getenv(jwt_secret_env, "") if jwt_secret_env else ""


def classify(route: RouteDefinition | None, comparison: bool = False) -> str:
    if route is None:
        return "UNKNOWN"
    if route.protected:
        return "USER_SPECIFIC_QUERY" if route.method == "GET" else "AUTH_REQUIRED_ACTION"
    return "PUBLIC_QUERY" if route.method == "GET" and not comparison else "PUBLIC_ACTION"


def auth_request(application: ApplicationDefinition, *, expired: bool = False) -> dict:
    config = application.authentication.public_config()
    message = (f"Your {application.name} session has expired. Please sign in again and try again."
               if expired else f"Please sign in to your {application.name} account first to use this feature.")
    return {"data": [], "execution_error": message, "auth_required": True, "auth_config": config}
