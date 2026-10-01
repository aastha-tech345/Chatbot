"""
ApplicationRegistry — DB-backed runtime application registry.

DATABASE IS THE SINGLE SOURCE OF TRUTH.
applications.json is NOT read during normal runtime.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from .models import ApplicationDefinition, AuthenticationConfig, ChatbotConfig, HTTPMethod, RouteDefinition, RouteStatus

logger = logging.getLogger(__name__)


class ApplicationRegistry:
    def __init__(self, registry_path: str | Path | None = None) -> None:
        self._applications: dict[str, ApplicationDefinition] = {}
        self._credentials: dict[str, dict[str, str]] = {}
        if registry_path is not None:
            self._load_from_json(Path(registry_path))

    async def initialize(self) -> None:
        await self._reload_from_db()
        for application in list(self._applications.values()):
            if application.discovery_mode in {"dynamic_openapi", "hybrid"} and application.openapi_url:
                logger.info("[REGISTRY] Starting OpenAPI discovery for app_id=%s", application.app_id)
                await self._discover_routes(application)
                logger.info("[REGISTRY] After discovery, app_id=%s has %d routes", application.app_id, len(application.routes))

    async def reload(self) -> None:
        await self._reload_from_db()

    async def get_fresh(self, app_id: str) -> ApplicationDefinition:
        """Read committed configuration for this request, including other workers' edits."""
        from .database import AsyncSessionLocal
        from .repositories import ApplicationRepo, ApplicationCredentialRepo, ApplicationRouteRepo
        from .crypto import decrypt
        from .policy_registry import load_policies

        async with AsyncSessionLocal() as db:
            db_app = await ApplicationRepo(db).get_by_app_id(app_id)
            if db_app is None or not db_app.is_enabled:
                self.remove_cached(app_id)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"APPLICATION_NOT_FOUND: Application '{app_id}' is not registered or not enabled.",
                )
            application, credentials = await self._build_definition(
                db_app, ApplicationCredentialRepo(db), ApplicationRouteRepo(db), decrypt,
            )
            config = db_app.chatbot_config_json
            policies = config.get("policies", []) if isinstance(config, dict) else []

        # Do not fall back to stale routes if the database read fails.
        self._applications[app_id] = application
        self._credentials[app_id] = credentials
        load_policies(app_id, policies if isinstance(policies, list) else [])
        return application

    def get(self, app_id: str) -> ApplicationDefinition:
        application = self._applications.get(app_id)
        if application is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"APPLICATION_NOT_FOUND: Application '{app_id}' is not registered or not enabled.",
            )
        logger.debug("[REGISTRY] Retrieved app_id=%s routes=%d", app_id, len(application.routes))
        return application

    def route(self, application: ApplicationDefinition, route_name: str) -> RouteDefinition:
        for route in application.routes:
            if route.name == route_name:
                return route
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The selected route is not registered for this application",
        )

    def remove_cached(self, app_id: str | None) -> None:
        self._applications.pop(app_id, None)
        self._credentials.pop(app_id, None)

    def set_cached_credentials(self, app_id: str, credentials: dict[str, str]) -> None:
        self._credentials[app_id] = credentials

    def get_service_key(self, app_id: str) -> str:
        return self._credentials.get(app_id, {}).get("service_key", "")

    def get_jwt_secret(self, app_id: str) -> str:
        return self._credentials.get(app_id, {}).get("jwt_secret", "")

    def get_app_credential(self, app_id: str, auth_type: str) -> str:
        return self._credentials.get(app_id, {}).get(auth_type, "")

    def status(self, app_id: str) -> dict[str, object]:
        application = self.get(app_id)
        return {
            "app_id": application.app_id,
            "name": application.name,
            "base_url": application.base_url,
            "enabled": bool(application.base_url),
            "route_count": len(application.routes),
        }

    def upsert(self, application: ApplicationDefinition) -> ApplicationDefinition:
        self._applications[application.app_id] = application
        return application

    def update_routes(self, app_id: str, routes: list[RouteDefinition]) -> ApplicationDefinition:
        existing = self.get(app_id)
        updated = existing.model_copy(update={"routes": routes})
        self._applications[app_id] = updated
        return updated

    def unregister(self, app_id: str) -> None:
        if app_id not in self._applications:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application is not registered")
        del self._applications[app_id]
        self._credentials.pop(app_id, None)

    def _load_from_json(self, registry_path: Path) -> None:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
        for item in raw.get("applications", []):
            mode = {"dynamic": "dynamic_openapi", "static": "manual"}.get(item.get("discovery_mode"), item.get("discovery_mode", "manual"))
            routes = item.get("routes") or []
            app_def = ApplicationDefinition.model_validate({**item, "discovery_mode": mode, "routes": routes})
            self._applications[app_def.app_id] = app_def
            self._credentials[app_def.app_id] = {"jwt_secret": "", "service_key": ""}
            if mode in {"dynamic_openapi", "hybrid"} and app_def.openapi_url:
                try:
                    asyncio.run(self._discover_routes(app_def))
                except RuntimeError:
                    logger.warning("OpenAPI discovery skipped because an event loop is already running")

    async def _reload_from_db(self) -> None:
        try:
            from .database import AsyncSessionLocal
            from .repositories import ApplicationRepo, ApplicationCredentialRepo, ApplicationRouteRepo
            from .crypto import decrypt
            from .policy_registry import load_policies

            async with AsyncSessionLocal() as db:
                app_repo = ApplicationRepo(db)
                cred_repo = ApplicationCredentialRepo(db)
                route_repo = ApplicationRouteRepo(db)
                db_apps = await app_repo.list_enabled()

                new_apps: dict[str, ApplicationDefinition] = {}
                new_creds: dict[str, dict[str, str]] = {}

                for db_app in db_apps:
                    try:
                        app_def, creds = await self._build_definition(db_app, cred_repo, route_repo, decrypt)
                        new_apps[app_def.app_id] = app_def
                        new_creds[app_def.app_id] = creds
                        raw_policies = []
                        if db_app.chatbot_config_json and isinstance(db_app.chatbot_config_json, dict):
                            raw_policies = db_app.chatbot_config_json.get("policies", [])
                        load_policies(app_def.app_id, raw_policies if isinstance(raw_policies, list) else [])
                        
                        # Log route availability breakdown
                        from .models import is_route_available, RouteStatus
                        all_routes = await route_repo.list_for_app(db_app.id)
                        available = sum(1 for r in all_routes if r.is_enabled and r.status == RouteStatus.AVAILABLE.value)
                        disabled = sum(1 for r in all_routes if not r.is_enabled or r.status == RouteStatus.DISABLED.value)
                        errored = sum(1 for r in all_routes if r.status == RouteStatus.ERROR.value)
                        
                        logger.info(
                            "[REGISTRY] Loaded app_id=%s routes_total=%d routes_available=%d routes_disabled=%d routes_error=%d",
                            app_def.app_id, len(all_routes), available, disabled, errored
                        )
                    except Exception as exc:
                        logger.error("[REGISTRY] Failed to build definition for app_id=%s error=%s", getattr(db_app, "app_id", "?"), exc)

            self._applications = new_apps
            self._credentials = new_creds
            
            # Log summary with breakdown
            from .models import RouteStatus
            total_routes = 0
            total_available = 0
            total_disabled = 0
            total_error = 0
            for app in new_apps.values():
                total_routes += len(app.routes)
                for route in app.routes:
                    if route.status == RouteStatus.AVAILABLE.value and route.is_enabled:
                        total_available += 1
                    elif route.status == RouteStatus.DISABLED.value or not route.is_enabled:
                        total_disabled += 1
                    elif route.status == RouteStatus.ERROR.value:
                        total_error += 1
            
            logger.info(
                "[REGISTRY] Loaded %d applications from DB total_routes=%d total_available=%d total_disabled=%d total_error=%d",
                len(new_apps), total_routes, total_available, total_disabled, total_error
            )

        except Exception as exc:
            logger.exception("[REGISTRY] Failed to reload from DB: %s", exc)
            if not self._applications:
                raise

    async def _build_definition(self, db_app: Any, cred_repo: Any, route_repo: Any, decrypt: Any) -> tuple[ApplicationDefinition, dict[str, str]]:
        jwt_secret = ""
        service_key = ""
        creds: dict[str, str] = {}
        credentials = await cred_repo.list_for_app(db_app.id)
        for cred in credentials:
            if not cred.is_active:
                continue
            try:
                if cred.auth_type == "jwt" and cred.api_key_encrypted:
                    jwt_secret = decrypt(cred.api_key_encrypted)
                elif cred.auth_type == "service_key" and cred.bearer_token_encrypted:
                    service_key = decrypt(cred.bearer_token_encrypted)
                elif cred.auth_type == "service_key" and cred.api_key_encrypted:
                    service_key = decrypt(cred.api_key_encrypted)
                elif cred.auth_type == "bearer" and cred.bearer_token_encrypted:
                    creds["bearer"] = decrypt(cred.bearer_token_encrypted)
                elif cred.auth_type == "api_key" and cred.api_key_encrypted:
                    creds["api_key"] = decrypt(cred.api_key_encrypted)
            except Exception as exc:
                logger.warning("[REGISTRY] Failed to decrypt credential app_id=%s cred_id=%s: %s", db_app.app_id, cred.id, exc)

        auth_config = AuthenticationConfig()
        if db_app.auth_config_json and isinstance(db_app.auth_config_json, dict):
            try:
                auth_config = AuthenticationConfig.model_validate(db_app.auth_config_json)
            except Exception as exc:
                logger.warning("[REGISTRY] Invalid auth_config_json for app_id=%s: %s", db_app.app_id, exc)

        # ShopNest owns customer sessions. Older registrations have no verification
        # configuration or shared JWT secret; validate with its existing identity API.
        raw_auth = db_app.auth_config_json or {}
        if (db_app.app_id == "ecommerce" and not jwt_secret
                and not raw_auth.get("user_info_path")
                and raw_auth.get("verification", "jwt") == "jwt"):
            auth_config = auth_config.model_copy(update={
                "verification": "introspection", "user_info_path": "/api/v1/auth/me",
            })

        chatbot_config = ChatbotConfig()
        if db_app.chatbot_config_json and isinstance(db_app.chatbot_config_json, dict):
            try:
                chatbot_config = ChatbotConfig.model_validate(db_app.chatbot_config_json)
            except Exception as exc:
                logger.warning("[REGISTRY] Invalid chatbot_config_json for app_id=%s: %s", db_app.app_id, exc)

        service_key_env = f"__db__{db_app.app_id}__service_key__"
        jwt_secret_env = f"__db__{db_app.app_id}__jwt_secret__"
        discovery_mode = {"dynamic": "dynamic_openapi", "static": "manual"}.get(db_app.discovery_mode, db_app.discovery_mode or "manual")
        db_routes = await route_repo.list_for_app(db_app.id)
        routes = [self._route_from_db(db_app.app_id, route) for route in db_routes if route.is_enabled]

        app_def = ApplicationDefinition(
            app_id=db_app.app_id,
            name=db_app.name,
            base_url=db_app.base_url or "",
            jwt_secret_env=jwt_secret_env,
            jwt_algorithm=db_app.jwt_algorithm or "HS256",
            service_key_env=service_key_env,
            openapi_url=db_app.openapi_url,
            discovery_mode=discovery_mode,
            routes=routes,
            authentication=auth_config,
            chatbot=chatbot_config,
        )
        creds.update({"jwt_secret": jwt_secret, "service_key": service_key})
        return app_def, creds

    def _route_from_db(self, app_id: str, route: Any) -> RouteDefinition:
        parameters: dict[str, str] = {}
        required: list[str] = []
        raw_parameters = route.parameters_json if isinstance(route.parameters_json, dict) else {}
        for key, value in raw_parameters.items():
            parameters[str(key)] = str(value)
        for collection in (route.query_params_json, route.path_params_json):
            if isinstance(collection, dict):
                for key, value in collection.items():
                    parameters[str(key)] = str(value.get("description") if isinstance(value, dict) else value)
                    if isinstance(value, dict) and value.get("required"):
                        required.append(str(key))
        return RouteDefinition(
            app_id=app_id,
            name=self._safe_route_name(route.operation_id or route.name or f"{route.method.lower()}_{route.id.replace('-', '_')}"),
            method=HTTPMethod(route.method),
            path=route.path,
            description=route.description or route.summary or route.operation_id or route.path,
            parameters=parameters,
            required_parameters=required,
            # Preserve the persisted access contract when rebuilding after a toggle.
            visibility="private" if route.auth_required else "public",
            requires_auth=bool(route.auth_required),
            authentication_strategy=route.auth_type,
            source=getattr(route, "source", "openapi") or "openapi",
            is_enabled=bool(getattr(route, "is_enabled", True)),
            status=RouteStatus.normalize(getattr(route, "status", None)),
        )

    async def _discover_routes(self, application: ApplicationDefinition) -> None:
        try:
            from .openapi_discovery import discover_openapi_routes
            logger.info("[OPENAPI] app=%s url=%s discovery_started", application.app_id, application.openapi_url)
            routes = await discover_openapi_routes(application.app_id, application.base_url, application.openapi_url)
            if routes:
                application.routes = routes
                logger.info("[OPENAPI] app=%s routes_discovered=%d", application.app_id, len(routes))
            else:
                logger.warning("[OPENAPI] app=%s routes_discovered=0", application.app_id)
        except Exception as exc:
            logger.error("OpenAPI discovery failed for app=%s error=%s", application.app_id, exc)

    def _safe_route_name(self, value: str) -> str:
        name = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
        if not name or not name[0].isalpha():
            name = f"route_{name or 'endpoint'}"
        return name


application_registry = ApplicationRegistry()
