"""OpenAPI discovery for explicitly chatbot-safe application routes."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx


_BLOCKED_PATH_PARTS = {
    "admin",
    "seller",
    "auth",
    "login",
    "register",
    "refresh",
    "webhook",
    "background",
    "internal",
    "assistant",
    "master-chatbot",
}
_OPERATIONS = {"get", "post", "put", "patch", "delete"}
_LOGGER = logging.getLogger(__name__)


class OpenAPIDiscoveryError(ValueError):
    """Raised when a safe route contract cannot be discovered."""


def discover_routes(openapi_url: str, *, timeout: float = 10.0) -> list[dict[str, Any]]:
    """Fetch an OpenAPI document and return only explicitly safe operations."""
    return _discover_routes_from_document(_fetch_openapi_document(openapi_url, timeout=timeout))


def discover_application_routes(
    base_url: str,
    *,
    openapi_url: str | None = None,
    api_prefix: str | None = None,
    timeout: float = 10.0,
) -> tuple[str, list[dict[str, Any]]]:
    """Discover routes from an application's root or configured OpenAPI location."""
    candidates = [_normalize_openapi_url(openapi_url)] if openapi_url else [
        _join_url(base_url, "openapi.json"),
    ]
    if not openapi_url and api_prefix:
        prefixed_url = _join_url(base_url, api_prefix, "openapi.json")
        if prefixed_url not in candidates:
            candidates.append(prefixed_url)

    errors: list[str] = []
    for candidate in candidates:
        _LOGGER.debug("Attempting OpenAPI discovery: %s", candidate)
        try:
            document = _fetch_openapi_document(candidate, timeout=timeout)
        except OpenAPIDiscoveryError as exc:
            reason = str(exc)
            errors.append(f"{candidate}: {reason}")
            _LOGGER.debug("Rejected OpenAPI URL %s: %s", candidate, reason)
            continue
        return candidate, _discover_routes_from_document(document)

    details = "; ".join(errors)
    raise OpenAPIDiscoveryError(f"Unable to fetch a valid OpenAPI document. Attempts: {details}")


def _fetch_openapi_document(openapi_url: str, *, timeout: float) -> dict[str, Any]:
    try:
        response = httpx.get(openapi_url, timeout=timeout)
        _LOGGER.debug("OpenAPI URL %s returned HTTP %s", openapi_url, response.status_code)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise OpenAPIDiscoveryError(f"HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise OpenAPIDiscoveryError(f"OpenAPI unavailable ({exc})") from exc
    except httpx.HTTPError as exc:
        raise OpenAPIDiscoveryError(f"OpenAPI HTTP error ({exc})") from exc
    try:
        document = response.json()
    except ValueError as exc:
        raise OpenAPIDiscoveryError("OpenAPI invalid JSON") from exc
    if (
        not isinstance(document, dict)
        or not isinstance(document.get("openapi"), str)
        or not document["openapi"]
        or not isinstance(document.get("paths"), dict)
    ):
        raise OpenAPIDiscoveryError("OpenAPI missing required openapi or paths fields")
    return document


def _normalize_openapi_url(openapi_url: str) -> str:
    normalized = openapi_url.strip().rstrip("/")
    if not normalized:
        raise OpenAPIDiscoveryError("MASTER_CHATBOT_OPENAPI_URL is invalid.")
    return normalized


def _join_url(base_url: str, *parts: str) -> str:
    root = base_url.strip().rstrip("/")
    if not root:
        raise OpenAPIDiscoveryError("MASTER_CHATBOT_API_BASE_URL is invalid.")
    suffix = "/".join(part.strip("/") for part in parts if part.strip("/"))
    return f"{root}/{suffix}" if suffix else root


def _discover_routes_from_document(document: dict[str, Any]) -> list[dict[str, Any]]:

    routes: list[dict[str, Any]] = []
    names: set[str] = set()
    for path, path_item in document["paths"].items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() not in _OPERATIONS or not isinstance(operation, dict):
                continue
            metadata = operation.get("x-master-chatbot")
            if not isinstance(metadata, dict) or metadata.get("enabled") is not True:
                continue
            if _is_blocked(path, operation):
                continue
            if method.lower() != "get" and metadata.get("allow_write") is not True:
                continue
            route_name = _route_name(operation.get("operationId"), method, path, names)
            names.add(route_name)
            description = metadata.get("description") or operation.get("summary") or operation.get("description")
            if not isinstance(description, str) or not description.strip():
                description = f"{method.upper()} {path}"
            routes.append(
                {
                    "name": route_name,
                    "method": method.upper(),
                    "path": path,
                    "description": description.strip(),
                    "parameters": _parameters(document, path_item, operation),
                }
            )
    return routes


def _is_blocked(path: str, operation: dict[str, Any]) -> bool:
    segments = {segment.lower() for segment in path.split("/") if segment and not segment.startswith("{")}
    tags = {str(tag).lower() for tag in operation.get("tags", [])}
    values = segments.union(tags)
    return any(blocked in value for value in values for blocked in _BLOCKED_PATH_PARTS)


def _route_name(operation_id: object, method: str, path: str, used: set[str]) -> str:
    candidate = str(operation_id or f"{method}_{path}").lower()
    candidate = re.sub(r"[^a-z0-9_]+", "_", candidate).strip("_")
    if not candidate or not candidate[0].isalpha():
        candidate = f"route_{candidate or 'operation'}"
    name = candidate
    suffix = 2
    while name in used:
        name = f"{candidate}_{suffix}"
        suffix += 1
    return name


def _parameters(document: dict[str, Any], path_item: dict[str, Any], operation: dict[str, Any]) -> dict[str, str]:
    parameters: dict[str, str] = {}
    for parameter in [*path_item.get("parameters", []), *operation.get("parameters", [])]:
        if not isinstance(parameter, dict) or parameter.get("in") not in {"path", "query"}:
            continue
        name = parameter.get("name")
        if isinstance(name, str) and name:
            parameters[name] = str(parameter.get("description") or f"{parameter.get('in')} parameter {name}")

    request_body = operation.get("requestBody")
    if isinstance(request_body, dict):
        schema = request_body.get("content", {}).get("application/json", {}).get("schema", {})
        schema = _resolve_schema(document, schema)
        if isinstance(schema, dict):
            for name, property_schema in schema.get("properties", {}).items():
                if isinstance(name, str) and isinstance(property_schema, dict):
                    parameters[name] = str(property_schema.get("description") or f"Request body field {name}")
    return parameters


def _resolve_schema(document: dict[str, Any], schema: object) -> object:
    if not isinstance(schema, dict) or not isinstance(schema.get("$ref"), str):
        return schema
    ref = schema["$ref"]
    if not ref.startswith("#/"):
        return schema
    value: object = document
    for part in ref[2:].split("/"):
        if not isinstance(value, dict):
            return schema
        value = value.get(part)
    return value
