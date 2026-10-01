"""
OpenAPI schema discovery and conversion to internal route definitions.

This module provides generic OpenAPI discovery for any OpenAPI 3.0+ application.
It fetches the schema at runtime, parses every path/method/parameter/requestBody,
and builds RouteDefinition objects dynamically — no hardcoded routes anywhere.
"""

from __future__ import annotations

import logging
import inspect
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .models import HTTPMethod, RouteDefinition

logger = logging.getLogger(__name__)

_OPENAPI_METHOD_MAP = {
    "get": HTTPMethod.GET,
    "post": HTTPMethod.POST,
    "put": HTTPMethod.PUT,
    "patch": HTTPMethod.PATCH,
    "delete": HTTPMethod.DELETE,
}


def _resolve_openapi_url(base_url: str, openapi_url: str) -> str:
    """Resolve relative OpenAPI schema locations against the app base URL."""
    if urlparse(openapi_url).scheme:
        return openapi_url
    if not base_url:
        return openapi_url
    return urljoin(f"{base_url.rstrip('/')}/", openapi_url.lstrip("/"))


def _generate_operation_id(method: str, path: str) -> str:
    """Generate a deterministic operation ID from HTTP method + path."""
    clean_path = (
        path.lstrip("/")
        .replace("/", "_")
        .replace("-", "_")
        .replace("{", "")
        .replace("}", "")
    )
    operation_id = f"{method.lower()}_{clean_path}"
    while "__" in operation_id:
        operation_id = operation_id.replace("__", "_")
    return operation_id.rstrip("_")


def _resolve_schema(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Follow a single $ref level to get the concrete schema object.
    
    components should be the top-level components dict:
    {"schemas": {"Foo": {...}}, "responses": {...}, ...}
    """
    if "$ref" in schema:
        ref_path = schema["$ref"]  # e.g. "#/components/schemas/AddCartItemRequest"
        parts = ref_path.lstrip("#/").split("/")
        # parts = ["components", "schemas", "AddCartItemRequest"]
        # components dict is already the top-level components object
        # so we need to skip the "components" prefix if present
        if parts and parts[0] == "components":
            parts = parts[1:]  # ["schemas", "AddCartItemRequest"]
        resolved = components
        for part in parts:
            if isinstance(resolved, dict):
                resolved = resolved.get(part, {})
        return resolved if isinstance(resolved, dict) else {}
    return schema


def _extract_parameter_info(
    parameters: list[dict[str, Any]] | None,
    request_body: dict[str, Any] | None,
    components: dict[str, Any] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """
    Extract all parameter names + descriptions from OpenAPI parameters and requestBody.

    Resolves $ref schemas one level deep so that nested request body fields
    (e.g. AddCartItemRequest, StripeCheckoutRequest) are fully extracted.

    Returns:
        (parameters_dict, required_parameters_list)
    """
    components = components or {}
    parameters_dict: dict[str, str] = {}
    required_parameters_list: list[str] = []

    # Path / query parameters
    if parameters:
        for param in parameters:
            if not isinstance(param, dict):
                continue
            param_name = param.get("name")
            if not param_name:
                continue
            param_in = param.get("in", "query")
            if param_in not in ("path", "query"):
                continue
            schema = param.get("schema", {})
            description = param.get("description") or schema.get("description") or f"{param_in} parameter"
            # Capture enum values in the description so the LLM can use them
            enum_vals = schema.get("enum") or (
                schema.get("anyOf", [{}])[0].get("enum") if schema.get("anyOf") else None
            )
            if enum_vals:
                description = f"{description} (allowed: {', '.join(str(v) for v in enum_vals)})"
            parameters_dict[param_name] = description
            if param.get("required"):
                required_parameters_list.append(param_name)

    # Request body
    if request_body:
        content = request_body.get("content", {})
        json_content = content.get("application/json", {})
        raw_schema = json_content.get("schema", {})
        schema = _resolve_schema(raw_schema, components)

        if schema:
            properties = schema.get("properties", {})
            body_required = schema.get("required", [])
            for prop_name, prop_schema in properties.items():
                if not isinstance(prop_schema, dict):
                    continue
                prop_description = prop_schema.get("description", "")
                # For array fields (e.g. items=[...]), describe element shape
                if prop_schema.get("type") == "array":
                    items_schema = _resolve_schema(prop_schema.get("items", {}), components)
                    if items_schema.get("properties"):
                        elem_keys = list(items_schema["properties"].keys())
                        elem_required = items_schema.get("required", [])
                        prop_description = (
                            prop_description
                            or f"Array of objects with fields: {', '.join(elem_keys)}"
                            f" (required per item: {', '.join(elem_required)})"
                        )
                    elif not prop_description:
                        prop_description = "Array field"
                parameters_dict[prop_name] = prop_description or "Request body field"
                if prop_name in body_required:
                    required_parameters_list.append(prop_name)

    return parameters_dict, required_parameters_list


def _extract_operation_visibility(
    operation: dict[str, Any],
    path: str | None = None,
) -> tuple[str, bool, bool]:
    """
    Determine visibility and auth requirements from operation metadata.

    The `path` can be passed explicitly or read from `operation["path"]` for
    backward-compatibility with tests that embed the path in the operation dict.

    Returns:
        (visibility, requires_auth, requires_user_context)
    """
    # Default: private / requires auth
    visibility = "private"
    requires_auth = True
    requires_user_context = False

    # Tags can hint at public routes
    tags = operation.get("tags", [])
    if tags and "public" in tags:
        visibility = "public"
        requires_auth = False

    # If the operation declares no security requirements → public
    security = operation.get("security")
    if security is not None and len(security) == 0:
        # Explicit empty security array: no auth required
        visibility = "public"
        requires_auth = False
    elif security is not None and len(security) > 0:
        # Explicit non-empty security: auth required
        visibility = "private"
        requires_auth = True
    # security is None (key absent): fall back to tag-based detection below

    # Treat well-known public catalog/search tags as public when no explicit security
    _PUBLIC_TAGS = {"catalog", "public", "search", "health", "recommendations"}
    if security is None and tags and any(t in _PUBLIC_TAGS for t in tags):
        visibility = "public"
        requires_auth = False

    # Resolve path — prefer explicit arg, then operation["path"] (legacy), else ""
    resolved_path = path or operation.get("path", "")
    path_lower = resolved_path.lower()

    # Endpoints under /me/ or user-specific patterns always require user context
    if any(
        pattern in path_lower
        for pattern in ["/me/", "/me}", "me_api", "/users/{", "/profile/", "/account/"]
    ):
        requires_user_context = True
        requires_auth = True
        visibility = "private"

    return visibility, requires_auth, requires_user_context


class OpenAPIDiscovery:
    """Discovers and converts OpenAPI operations to internal RouteDefinition objects."""

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    async def discover(
        self,
        app_id: str,
        base_url: str,
        openapi_url: str,
    ) -> list[RouteDefinition]:
        """
        Fetch and parse an OpenAPI schema, returning one RouteDefinition per operation.

        Logs:
            [OPENAPI] app=<app_id>
            [OPENAPI] url=<url>
            [OPENAPI] discovery_started
            [OPENAPI] response_status=<status>
            [OPENAPI] paths_found=<count>
            [OPENAPI] routes_discovered=<count>
        """
        logger.info(f"[OPENAPI] app={app_id}")
        resolved_openapi_url = _resolve_openapi_url(base_url, openapi_url)

        logger.info(f"[OPENAPI] url={resolved_openapi_url}")
        logger.info("[OPENAPI] discovery_started")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(resolved_openapi_url)
        except httpx.RequestError as e:
            logger.error(f"[OPENAPI] app={app_id} fetch_error={e}")
            raise RuntimeError(f"Cannot fetch OpenAPI schema: {e}") from e

        logger.info(f"[OPENAPI] response_status={response.status_code}")

        if response.status_code != 200:
            raise RuntimeError(f"OpenAPI fetch returned status {response.status_code}")

        try:
            openapi_schema = response.json()
            if inspect.isawaitable(openapi_schema):
                openapi_schema = await openapi_schema
        except ValueError as e:
            logger.error(f"[OPENAPI] app={app_id} json_parse_error={e}")
            raise RuntimeError(f"Invalid OpenAPI JSON: {e}") from e

        if not isinstance(openapi_schema, dict):
            raise RuntimeError("OpenAPI schema must be a JSON object")

        openapi_version = openapi_schema.get("openapi", "unknown")
        logger.info(f"[OPENAPI] app={app_id} openapi_version={openapi_version}")

        components = openapi_schema.get("components", {})
        paths = openapi_schema.get("paths", {})

        logger.info(f"[OPENAPI] paths_found={len(paths)}")

        if not paths:
            logger.warning(f"[OPENAPI] app={app_id} no_paths_in_schema")
            return []

        routes: list[RouteDefinition] = []

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            for method_str, operation in path_item.items():
                if not isinstance(operation, dict):
                    continue
                if method_str not in _OPENAPI_METHOD_MAP:
                    continue

                # Operation ID
                operation_id = operation.get("operationId")
                if not operation_id:
                    operation_id = _generate_operation_id(method_str, path)
                    logger.debug(f"[OPENAPI] generated_id={operation_id} method={method_str} path={path}")
                else:
                    # Simplify verbose FastAPI operationIds like "add_cart_item_api_v1_cart_items_post"
                    # Keep the leading meaningful segment, drop the `_api_v*_..._method` suffix
                    if "_api_v" in operation_id:
                        parts = operation_id.split("_api_v")
                        operation_id = parts[0]
                    logger.debug(f"[OPENAPI] operation_id={operation_id} method={method_str} path={path}")

                summary = operation.get("summary", "")
                description = operation.get("description") or summary or "API operation"

                parameters = operation.get("parameters", [])
                request_body = operation.get("requestBody")

                params_dict, required_params = _extract_parameter_info(
                    parameters, request_body, components
                )

                visibility, requires_auth, requires_user_context = (
                    _extract_operation_visibility(operation, path)
                )

                route = RouteDefinition(
                    name=operation_id,
                    method=_OPENAPI_METHOD_MAP[method_str],
                    path=path,
                    description=description,
                    parameters=params_dict,
                    required_parameters=required_params,
                    app_id=app_id,
                    visibility=visibility,
                    requires_auth=requires_auth,
                    requires_user_context=requires_user_context,
                    allowed_roles=[],
                    supported_operations=[],
                    authentication_strategy=None,
                )
                routes.append(route)

        logger.info(f"[OPENAPI] routes_discovered={len(routes)}")
        logger.info(f"[OPENAPI] app={app_id} discovery_complete paths={len(paths)} routes={len(routes)}")
        return routes


_discovery = OpenAPIDiscovery()


async def discover_openapi_routes(
    app_id: str,
    base_url: str,
    openapi_url: str,
) -> list[RouteDefinition]:
    """Public API: discover routes from an OpenAPI schema URL."""
    return await _discovery.discover(app_id, base_url, openapi_url)
