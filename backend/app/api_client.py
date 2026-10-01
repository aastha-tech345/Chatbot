from __future__ import annotations

import logging
import time
from string import Formatter
from urllib.parse import quote
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select

from .sanitization import safe_data
from .authorization import normalize_authorization, service_headers
from .models import ApplicationDefinition, HTTPMethod, RouteDefinition, RouteStatus, is_route_disabled

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = {"authorization", "api_key", "service_key", "token", "secret", "password"}

_READ_METHODS = {HTTPMethod.GET}
_WRITE_METHODS = {HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH, HTTPMethod.DELETE}


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
    """Executes application routes discovered from OpenAPI or registered statically."""

    async def execute(
        self,
        *,
        application: ApplicationDefinition,
        route: RouteDefinition,
        parameters: dict[str, Any],
        authorization: str | None,
        request_id: str,
    ) -> Any:
        # ─────────────────────────────────────────────────────────────────────
        # CRITICAL: Fresh database lookup before execution
        # ─────────────────────────────────────────────────────────────────────
        # Even if the planner received this route from cache or if the
        # route was disabled AFTER planning, we perform a FRESH database check here.
        # This protects against stale in-memory route metadata.
        try:
            from .database import AsyncSessionLocal
            from .repositories import ApplicationRepo
            from .db_models import ApplicationRoute
            
            async with AsyncSessionLocal() as db:
                app_repo = ApplicationRepo(db)
                
                # Verify application is still enabled
                db_app = await app_repo.get_by_app_id(application.app_id)
                if not db_app or not db_app.is_enabled:
                    logger.warning(
                        "[ROUTE_GUARD_FRESH] app=%s action=blocked reason=application_disabled",
                        application.app_id
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="ROUTE_DISABLED",
                    )
                
                # Perform fresh lookup of the route by method + path from the database
                r = await db.execute(
                    select(ApplicationRoute).where(
                        ApplicationRoute.application_id == db_app.id,
                        ApplicationRoute.method == route.method.value,
                        ApplicationRoute.path == route.path,
                    )
                )
                db_route = r.scalar_one_or_none()
                
                if not db_route:
                    logger.warning(
                        "[ROUTE_GUARD_FRESH] app=%s route_name=%s method=%s path=%s action=blocked reason=route_not_found",
                        application.app_id, route.name, route.method.value, route.path
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="ROUTE_DISABLED",
                    )
                
                # Check if route is disabled in fresh DB state
                if not db_route.is_enabled or db_route.status in {RouteStatus.DISABLED.value, RouteStatus.ERROR.value}:
                    logger.warning(
                        "[ROUTE_GUARD_FRESH] app=%s route_name=%s status=%s is_enabled=%s action=blocked",
                        application.app_id, db_route.name, db_route.status, db_route.is_enabled
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="ROUTE_DISABLED",
                    )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[ROUTE_GUARD_FRESH] app=%s route_name=%s error=%s", application.app_id, route.name, exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ROUTE_DISABLED",
            ) from exc
        
        authorization = normalize_authorization(authorization)
        if route.protected and not authorization:
            raise HTTPException(status_code=401, detail="Authentication required")

        # Only pass parameters that are actually declared on the route
        safe_parameters = {
            key: value
            for key, value in parameters.items()
            if key in route.parameters and value is not None
        }

        # Identify path parameter names from the route path template
        path_parameter_names = {
            field_name
            for _, field_name, _, _ in Formatter().parse(route.path)
            if field_name
        }

        # Validate all required path parameters are present
        missing_path_parameters = path_parameter_names - safe_parameters.keys()
        if missing_path_parameters:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required path parameters: {', '.join(sorted(missing_path_parameters))}",
            )

        # Substitute path parameters into the URL (URL-encode each value)
        path = route.path.format(
            **{name: quote(str(safe_parameters[name]), safe="") for name in path_parameter_names}
        )

        # Non-path parameters are either query params (GET) or request body (POST/PUT/PATCH)
        # DELETE with no body: no extra params needed
        non_path_parameters = {
            key: value
            for key, value in safe_parameters.items()
            if key not in path_parameter_names
        }

        target_url = f"{application.base_url.rstrip('/')}{path}"

        logger.info(
            "[API] app=%s operation=%s method=%s path=%s request_started request_id=%s",
            application.app_id,
            route.name,
            route.method.value,
            path,
            request_id,
        )

        is_read = route.method in _READ_METHODS

        headers: dict[str, str] = {"X-Request-Id": request_id, **service_headers(application)}
        if route.protected and authorization:
            headers["Authorization"] = authorization
        if not is_read:
            headers["Idempotency-Key"] = request_id

        started = time.perf_counter()
        response: httpx.Response | None = None
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.request(
                    route.method.value,
                    target_url,
                    params=non_path_parameters if is_read else None,
                    json=non_path_parameters if not is_read and non_path_parameters else None,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            await self._record_log(
                application=application,
                route=route,
                request_id=request_id,
                path=path,
                status_code=None,
                response_time_ms=elapsed_ms,
                status_text="FAILED",
                level="ERROR",
                message=f"{route.name} request failed",
                error_code=type(exc).__name__,
                error_message=type(exc).__name__,
            )
            logger.exception(
                "[API] request_failed app=%s operation=%s method=%s path=%s status=unavailable request_id=%s exc_type=%s message=%s parameters=%s",
                application.app_id,
                route.name,
                route.method.value,
                path,
                request_id,
                type(exc).__name__,
                type(exc).__name__,
                safe_data(safe_parameters),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The application service is currently unavailable.",
            ) from exc

        status_code = response.status_code
        success = status_code < 400
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        await self._record_log(
            application=application,
            route=route,
            request_id=request_id,
            path=path,
            status_code=status_code,
            response_time_ms=elapsed_ms,
            status_text="SUCCESS" if success else "FAILED",
            level="SUCCESS" if success else ("WARNING" if status_code < 500 else "ERROR"),
            message=f"{route.name} returned {status_code}",
            error_code=None if success else str(status_code),
            error_message=None if success else f"Application returned HTTP {status_code}",
        )
        logger.info(
            "[API] app=%s operation=%s method=%s path=%s response_status=%s success=%s request_id=%s",
            application.app_id,
            route.name,
            route.method.value,
            path,
            status_code,
            success,
            request_id,
        )

        if not success:
            body_summary = "[response body omitted]"
            logger.warning(
                "[API] app=%s operation=%s method=%s path=%s status=%s error_body=%s request_id=%s",
                application.app_id,
                route.name,
                route.method.value,
                path,
                status_code,
                body_summary,
                request_id,
            )

        if status_code in {401, 403}:
            raise HTTPException(
                status_code=status_code,
                detail="You are not authorized to access this information.",
            )
        if status_code == 404:
            raise HTTPException(status_code=404, detail="The requested resource was not found.")
        if status_code in {400, 409, 422}:
            try:
                error_body = response.json()
            except ValueError:
                error_body = {}
            detail = error_body.get("detail") if isinstance(error_body, dict) else None
            if isinstance(detail, str) and detail:
                message = detail
            elif isinstance(detail, list):
                messages = [
                    str(item.get("msg"))
                    for item in detail
                    if isinstance(item, dict) and item.get("msg")
                ]
                message = "; ".join(messages) or "Please check the supplied details and try again."
            else:
                message = "Please check the supplied details and try again."
            raise HTTPException(
                status_code=status_code,
                detail=message,
            )
        if status_code >= 500:
            body_summary = "[response body omitted]"
            detail = (
                "Application service 5xx response "
                f"status={status_code} route={route.name} body={body_summary}"
            )
            if not is_read:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=detail,
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=detail,
            )
        if status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Application service unexpected error status={status_code} route={route.name}",
            )
        if status_code == 204:
            return {"status": "success"}
        try:
            return safe_data(response.json())
        except ValueError as exc:
            logger.exception(
                "[API] invalid_json_response app=%s operation=%s method=%s path=%s request_id=%s exc_type=%s message=%s body=%s",
                application.app_id,
                route.name,
                route.method.value,
                path,
                request_id,
                type(exc).__name__,
                exc,
                "[response body omitted]",
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"The application returned invalid JSON for route={route.name}: {type(exc).__name__}: {exc}",
            ) from exc

    async def _record_log(
        self,
        *,
        application: ApplicationDefinition,
        route: RouteDefinition,
        request_id: str,
        path: str,
        status_code: int | None,
        response_time_ms: float,
        status_text: str,
        level: str,
        message: str,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        try:
            from .database import AsyncSessionLocal
            from .repositories import ApiRequestLogRepo, ApplicationRepo

            async with AsyncSessionLocal() as db:
                app = await ApplicationRepo(db).get_by_app_id(application.app_id)
                await ApiRequestLogRepo(db).create({
                    "application_id": app.id if app else None,
                    "method": route.method.value,
                    "endpoint": path,
                    "source": route.source,
                    "request_id": request_id,
                    "status_code": status_code,
                    "status": status_text,
                    "level": level,
                    "message": message,
                    "response_time_ms": response_time_ms,
                    "error_code": error_code,
                    "error_message": error_message,
                    "request_meta_json": {"route_name": route.name},
                })
                await db.commit()
        except Exception as exc:
            logger.warning("[API] request_log_failed app=%s route=%s request_id=%s error=%s", application.app_id, route.name, request_id, exc)
