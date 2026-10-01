from __future__ import annotations

import logging
from string import Formatter
from urllib.parse import quote
from typing import Any

import httpx
from fastapi import HTTPException, status

from .sanitization import safe_data
from .models import ApplicationDefinition, RouteDefinition

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = {"authorization", "api_key", "service_key", "token", "secret", "password"}


def _safe_response_body(response: httpx.Response) -> object:
    try:
        body = response.json()
    except ValueError:
        return response.text[:500]
    if not isinstance(body, dict):
        return body
    return {
        key: "[REDACTED]" if key.lower() in _SENSITIVE_KEYS else value
        for key, value in body.items()
    }


class ApplicationAPIClient:
    """Executes only application routes explicitly registered by the application."""

    async def execute(
        self,
        *,
        application: ApplicationDefinition,
        route: RouteDefinition,
        parameters: dict[str, Any],
        authorization: str | None,
        request_id: str,
    ) -> Any:
        if route.protected and not authorization:
            raise HTTPException(status_code=401, detail="Authentication required")
        safe_parameters = {
            key: value
            for key, value in parameters.items()
            if key in route.parameters and value is not None
        }
        path_parameter_names = {
            field_name
            for _, field_name, _, _ in Formatter().parse(route.path)
            if field_name
        }
        missing_path_parameters = path_parameter_names - safe_parameters.keys()
        if missing_path_parameters:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The selected route requires additional path parameters.",
            )
        path = route.path.format(**{name: quote(str(safe_parameters[name]), safe="") for name in path_parameter_names})
        request_parameters = {
            key: value for key, value in safe_parameters.items() if key not in path_parameter_names
        }
        target_url = f"{application.base_url.rstrip('/')}{path}"
        logger.info(
            "[CHAT] application API request app_id=%s tool=%s target_url=%s method=%s request_id=%s",
            application.app_id,
            route.name,
            target_url,
            route.method,
            request_id,
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.request(
                    route.method,
                    target_url,
                    params=request_parameters if route.method == "GET" else None,
                    json=request_parameters if route.method != "GET" else None,
                    headers={**({"Authorization": authorization} if route.protected and authorization else {}), "X-Request-Id": request_id, **({"Idempotency-Key": request_id} if route.method != "GET" else {})},
                )
        except httpx.HTTPError as exc:
            logger.warning(
                "[CHAT] application API response app_id=%s tool=%s target_url=%s method=%s status=unavailable success=false request_id=%s",
                application.app_id,
                route.name,
                target_url,
                route.method,
                request_id,
            )
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="The application service is currently unavailable.") from exc
        logger.info(
            "[CHAT] application API response app_id=%s tool=%s target_url=%s method=%s status=%s success=%s error_body=%s request_id=%s",
            application.app_id,
            route.name,
            target_url,
            route.method,
            response.status_code,
            response.status_code < 400,
            "<omitted>" if response.status_code >= 400 else "<success>",
            request_id,
        )
        if response.status_code in {401, 403}:
            raise HTTPException(status_code=response.status_code, detail="You are not authorized to access this information.")
        if response.status_code in {400, 404, 409, 422}:
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            raise HTTPException(status_code=response.status_code, detail=detail[:500] if isinstance(detail, str) else "Please check the supplied details and try again.")
        if response.status_code >= 400:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="The application service could not complete this request.")
        if response.status_code == 204:
            return {"status": "success"}
        try:
            return safe_data(response.json())
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="The application returned an invalid response.") from exc
