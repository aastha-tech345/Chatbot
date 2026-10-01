"""
Service layer — business logic between repositories and routes.
Routes call services; services call repositories.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .crypto import (
    hash_password, verify_password, encrypt, decrypt, mask,
    create_access_token, create_refresh_token, hash_refresh_token,
)
from .repositories import (
    AdminUserRepo, AdminSessionRepo, ApplicationRepo, ApplicationRouteRepo, ApplicationCredentialRepo,
    AIProviderRepo, AICredentialRepo, ConversationRepo, ApiRequestLogRepo,
    AuditLogRepo, GlobalSettingRepo,
)
from .db_models import AdminUser, AICredential

logger = logging.getLogger(__name__)


# ─── Authentication ──────────────────────────────────────────────────────────

ACCESS_TOKEN_EXPIRE_SECONDS  = int(os.getenv("ACCESS_TOKEN_EXPIRE_SECONDS",  "3600"))
REFRESH_TOKEN_EXPIRE_SECONDS = int(os.getenv("REFRESH_TOKEN_EXPIRE_SECONDS", "604800"))  # 7 days


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db   = db
        self.repo = AdminUserRepo(db)
        self.sess = AdminSessionRepo(db)
        self.audit = AuditLogRepo(db)

    async def login(self, email: str, password: str, request: Request | None = None) -> dict:
        ip  = request.client.host if request and request.client else None
        ua  = request.headers.get("user-agent") if request else None

        user = await self.repo.get_by_email(email)
        if not user or not user.is_active:
            await self.audit.record(action="login_failed", description=f"Unknown email: {email}", ip_address=ip, user_agent=ua)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

        if not verify_password(password, user.password_hash):
            await self.audit.record(action="login_failed", admin_user_id=user.id, ip_address=ip, user_agent=ua)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

        await self.repo.update_last_login(user.id)

        access_token  = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
        refresh_token = create_refresh_token()
        token_hash    = hash_refresh_token(refresh_token)
        expires_at    = datetime.now(timezone.utc) + timedelta(seconds=REFRESH_TOKEN_EXPIRE_SECONDS)

        await self.sess.create(
            admin_user_id=user.id, refresh_token_hash=token_hash,
            expires_at=expires_at, ip_address=ip, user_agent=ua,
        )
        await self.audit.record(action="login_success", admin_user_id=user.id, ip_address=ip, user_agent=ua)

        return {
            "access_token":  access_token,
            "refresh_token": refresh_token,
            "token_type":    "bearer",
            "expires_in":    ACCESS_TOKEN_EXPIRE_SECONDS,
            "user": _user_schema(user),
        }

    async def logout(self, refresh_token: str, admin_user_id: str) -> None:
        token_hash = hash_refresh_token(refresh_token)
        session    = await self.sess.get_active(token_hash)
        if session:
            await self.sess.revoke(session.id)
        await self.audit.record(action="logout", admin_user_id=admin_user_id)

    async def refresh(self, refresh_token: str) -> dict:
        token_hash = hash_refresh_token(refresh_token)
        session    = await self.sess.get_active(token_hash)
        if not session:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired. Please log in again.")

        user = await self.repo.get_by_id(session.admin_user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is inactive.")

        access_token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
        return {"access_token": access_token, "token_type": "bearer", "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS}

    async def me(self, admin_user_id: str) -> dict:
        user = await self.repo.get_by_id(admin_user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        return _user_schema(user)

    async def change_password(self, admin_user_id: str, current_password: str, new_password: str) -> dict:
        user = await self.repo.get_by_id(admin_user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        if not verify_password(current_password, user.password_hash):
            await self.audit.record(action="password_change_failed", admin_user_id=admin_user_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
        if verify_password(new_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be different from current password.")

        await self.repo.update_password_hash(admin_user_id, hash_password(new_password))
        await self.sess.revoke_all_for_user(admin_user_id)
        await self.audit.record(action="password_changed", admin_user_id=admin_user_id)
        return {"success": True}

    async def create_admin(self, *, email: str, password: str, full_name: str) -> dict:
        existing = await self.repo.get_by_email(email)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")
        user = await self.repo.create(
            email=email, password_hash=hash_password(password), full_name=full_name
        )
        await self.audit.record(action="admin_user_created", entity_type="admin_user", entity_id=user.id)
        return _user_schema(user)

    async def has_any_admin(self) -> bool:
        return await self.repo.exists()


# ─── Applications ────────────────────────────────────────────────────────────

class ApplicationService:
    def __init__(self, db: AsyncSession):
        self.db         = db
        self.repo       = ApplicationRepo(db)
        self.route_repo = ApplicationRouteRepo(db)
        self.audit      = AuditLogRepo(db)
        self.credential_repo = ApplicationCredentialRepo(db)

    async def list_all(self) -> list[dict]:
        apps = await self.repo.list_all()
        return [
            await self._schema(a, route_count=await self.route_repo.count_for_app(a.id))
            for a in apps
        ]

    async def list_paginated(
        self,
        page: int,
        page_size: int,
        *,
        search: str | None = None,
        status: str | None = None,
        application_type: str | None = None,
        category: str | None = None,
        is_enabled: bool | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict:
        """List applications with server-side pagination and filtering."""
        result = await self.repo.list_paginated(
            page=page,
            page_size=page_size,
            search=search,
            status=status,
            application_type=application_type,
            category=category,
            is_enabled=is_enabled,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        items = result["items"]
        apps_schema = [
            await self._schema(a, route_count=await self.route_repo.count_for_app(a.id))
            for a in items
        ]
        return {
            "items": apps_schema,
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
            "total_pages": result["total_pages"],
        }

    async def get(self, uid: str) -> dict:
        app = await self.repo.get_by_id(uid)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found.")
        return await self._schema(app, route_count=await self.route_repo.count_for_app(app.id))

    async def create(self, data: dict, admin_user_id: str | None = None) -> dict:
        data = dict(data)
        secret = self._pop_service_key(data)
        if data.get("auth_type") == "service_key" and not secret:
            raise HTTPException(422, "Master Chatbot Service Key is required.")
        # Validate app_id uniqueness
        existing = await self.repo.get_by_app_id(data.get("app_id", ""))
        if existing:
            raise HTTPException(status_code=409, detail="app_id already registered.")
        data["discovery_mode"] = _normalize_discovery_mode(
            data.get("discovery_mode"),
            has_openapi=bool(data.get("openapi_url")),
        )
        data.setdefault("is_enabled", data.get("status") != "inactive")
        app = await self.repo.create(data)
        await self._save_service_key(app.id, secret)
        await self.audit.record(action="application_created", admin_user_id=admin_user_id,
                                entity_type="application", entity_id=app.id,
                                description=f"Registered {app.name} ({app.app_id})")
        await self._publish(app)
        return await self._schema(app, route_count=0)

    async def update(self, uid: str, data: dict, admin_user_id: str | None = None) -> dict:
        data = dict(data)
        secret = self._pop_service_key(data)
        current = await self.repo.get_by_id(uid)
        if not current:
            raise HTTPException(404, "Application not found.")
        old_app_id = current.app_id
        if data.get("auth_type", current.auth_type) == "service_key" and not secret and not await self._configured(uid):
            raise HTTPException(422, "Master Chatbot Service Key is required.")
        if "status" in data and "is_enabled" not in data:
            data["is_enabled"] = data["status"] != "inactive"
        if "app_id" in data:
            existing = await self.repo.get_by_app_id(data["app_id"])
            if existing and existing.id != uid:
                raise HTTPException(status_code=409, detail="app_id already registered.")
        if "discovery_mode" in data or "openapi_url" in data:
            current = await self.repo.get_by_id(uid)
            has_openapi = bool(data.get("openapi_url") if "openapi_url" in data else getattr(current, "openapi_url", None))
            data["discovery_mode"] = _normalize_discovery_mode(data.get("discovery_mode") or getattr(current, "discovery_mode", None), has_openapi=has_openapi)
        app = await self.repo.update(uid, data)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found.")
        await self._save_service_key(app.id, secret)
        await self.audit.record(action="application_updated", admin_user_id=admin_user_id,
                                entity_type="application", entity_id=uid)
        await self._publish(app, old_app_id)
        return await self._schema(app, route_count=await self.route_repo.count_for_app(app.id))

    async def delete(self, uid: str, admin_user_id: str | None = None) -> bool:
        current = await self.repo.get_by_id(uid)
        old_app_id = current.app_id if current else None
        ok = await self.repo.delete(uid)
        if not ok:
            raise HTTPException(status_code=404, detail="Application not found.")
        await self.audit.record(action="application_deleted", admin_user_id=admin_user_id,
                                entity_type="application", entity_id=uid)
        await self.db.commit()
        from .app_registry import application_registry
        application_registry.remove_cached(old_app_id)
        return True


    @staticmethod
    def _pop_service_key(data: dict) -> str | None:
        secret = data.pop("service_key", None)
        if secret is not None and hasattr(secret, "get_secret_value"):
            secret = secret.get_secret_value()
        # Preserve exact secret bytes; blank edits never erase an existing key.
        return secret if secret and secret.strip() else None

    async def _configured(self, uid: str) -> bool:
        credential = await self.credential_repo.get_active_for_app(uid, "service_key")
        return bool(credential and (credential.bearer_token_encrypted or credential.api_key_encrypted))

    async def _schema(self, app, route_count: int) -> dict:
        return {**_app_schema(app, route_count=route_count),
                "service_key_configured": await self._configured(app.id)}

    async def _save_service_key(self, uid: str, secret: str | None) -> None:
        if secret:
            await self.credential_repo.upsert(uid, "service_key", {
                "bearer_token_encrypted": encrypt(secret), "api_key_encrypted": None,
                "is_active": True,
            })

    async def _publish(self, app, old_app_id: str | None = None) -> None:
        from .app_registry import application_registry
        # Build against this transaction; publish only after durable commit.
        definition, credentials = await application_registry._build_definition(
            app, self.credential_repo, self.route_repo, decrypt)
        await self.db.commit()
        application_registry.remove_cached(old_app_id or app.app_id)
        if app.is_enabled:
            application_registry.upsert(definition)
            application_registry.set_cached_credentials(app.app_id, credentials)


# ─── Application Routes ───────────────────────────────────────────────────────

class ApplicationRouteService:
    def __init__(self, db: AsyncSession):
        self.db        = db
        self.app_repo  = ApplicationRepo(db)
        self.route_repo = ApplicationRouteRepo(db)
        self.audit     = AuditLogRepo(db)

    async def list_for_app(self, application_id: str) -> list[dict]:
        routes = await self.route_repo.list_for_app(application_id)
        return [_route_schema(r) for r in routes]

    async def list_for_app_paginated(
        self,
        application_id: str,
        page: int,
        page_size: int,
        *,
        search: str | None = None,
        method: str | None = None,
        status: str | None = None,
    ) -> dict:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        total = await self.route_repo.count_for_app(
            application_id,
            search=search,
            method=method,
            status=status,
        )
        routes = await self.route_repo.list_for_app(
            application_id,
            offset=(page - 1) * page_size,
            limit=page_size,
            search=search,
            method=method,
            status=status,
        )
        return {
            "items": [_route_schema(r) for r in routes],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def persist_discovered_routes(self, application_id: str, routes: list[dict]) -> int:
        """Save discovered OpenAPI routes to DB as a cache/snapshot."""
        from .models import RouteStatus
        for route in routes:
            route.setdefault("source", "openapi")
            # Normalize status to canonical form (discovered routes default to available)
            if "status" not in route:
                route["status"] = RouteStatus.AVAILABLE.value
            else:
                route["status"] = RouteStatus.normalize(route["status"])
        await self.route_repo.upsert_routes(application_id, routes, source="openapi")
        await self.app_repo.update_discovery_timestamp(application_id)
        return len(routes)

    async def create_manual_route(self, application_id: str, data: dict, admin_user_id: str | None = None) -> dict:
        app = await self.app_repo.get_by_id(application_id)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found.")
        route = await self.route_repo.create(application_id, _manual_route_data(data))
        await self.audit.record(action="manual_route_created", admin_user_id=admin_user_id,
                                entity_type="application_route", entity_id=route.id)
        return _route_schema(route)

    async def update_manual_route(self, route_id: str, data: dict, admin_user_id: str | None = None) -> dict:
        route = await self.route_repo.get_by_id(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="Route not found.")
        if route.source != "manual":
            raise HTTPException(status_code=400, detail="Only manual routes can be edited directly.")
        updated = await self.route_repo.update(route_id, _manual_route_data(data, partial=True))
        await self.audit.record(action="manual_route_updated", admin_user_id=admin_user_id,
                                entity_type="application_route", entity_id=route_id)
        return _route_schema(updated)

    async def delete_manual_route(self, route_id: str, admin_user_id: str | None = None) -> None:
        route = await self.route_repo.get_by_id(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="Route not found.")
        if route.source != "manual":
            raise HTTPException(status_code=400, detail="OpenAPI routes should be disabled, not deleted manually.")
        await self.route_repo.delete(route_id)
        await self.audit.record(action="manual_route_deleted", admin_user_id=admin_user_id,
                                entity_type="application_route", entity_id=route_id)

    async def test_route(
        self,
        route_id: str,
        admin_user_id: str | None = None,
        *,
        headers: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        body: Any = None,
        method: str | None = None,
    ) -> dict:
        route = await self.route_repo.get_by_id(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="Route not found.")
        app = await self.app_repo.get_by_id(route.application_id)
        if not app:
            raise HTTPException(status_code=404, detail="Application not found.")
        if route.full_url:
            parsed_base = urlparse(app.base_url)
            parsed_full = urlparse(route.full_url)
            if parsed_full.scheme not in {"http", "https"} or parsed_full.netloc != parsed_base.netloc:
                raise HTTPException(status_code=400, detail="Absolute route URLs must stay on the application host.")
            url = route.full_url
        else:
            url = urljoin(app.base_url.rstrip("/") + "/", route.path.lstrip("/"))
        request_headers = _safe_headers(route.headers_json or {})
        request_headers.update(_request_scoped_headers(headers or {}))
        has_authorization = _has_header(request_headers, "Authorization")
        logger.info("[API_TEST] authorization_header_present=%s", has_authorization)
        logger.info("[API_TEST] forwarding_authorization=%s", has_authorization)
        if getattr(route, "auth_required", False) and not has_authorization:
            return {
                "success": False,
                "status_code": status.HTTP_401_UNAUTHORIZED,
                "response_time_ms": 0,
                "body": {"detail": "Authorization header is required for this endpoint."},
            }
        if route.content_type:
            request_headers.setdefault("Content-Type", route.content_type)
        request_method = (method or route.method).upper()
        params = query_params if query_params is not None else _param_values(route.query_params_json)
        json_body = body if body is not None else (route.request_body_json if route.request_body_json else None)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.request(
                    request_method,
                    url,
                    params=params,
                    json=json_body if request_method not in {"GET", "HEAD"} else None,
                    headers=request_headers,
                )
        except httpx.HTTPError as exc:
            return {"success": False, "error": type(exc).__name__, "message": "API test failed."}
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "success": response.status_code < 400,
            "status_code": response.status_code,
            "response_time_ms": elapsed_ms,
            "headers": _display_headers(dict(response.headers)),
            "body": _safe_response(response),
        }

    async def update_route_status(self, route_id: str, enabled: bool,
                                  admin_user_id: str | None = None) -> None:
        from .models import RouteStatus
        import logging
        
        new_status = RouteStatus.normalize("available" if enabled else "disabled")
        route = await self.route_repo.get_by_id(route_id)
        if not route:
            raise HTTPException(status_code=404, detail="Route not found.")
        
        await self.route_repo.update_status(route_id, new_status, enabled)
        action = "route_enabled" if enabled else "route_disabled"
        await self.audit.record(action=action, admin_user_id=admin_user_id,
                                entity_type="application_route", entity_id=route_id)
        
        # reload() reads through a separate database session. Commit the status
        # and audit entry first so it sees this toggle, not the previous value.
        # Waiting for get_db's cleanup commit leaves the registry one toggle behind.
        await self.db.commit()

        from .app_registry import application_registry
        logger = logging.getLogger(__name__)
        try:
            logger.info("[CACHE_INVALIDATION] Reloading application registry after route status change route_id=%s enabled=%s", route_id, enabled)
            await application_registry.reload()
            logger.info("[CACHE_INVALIDATION] Application registry reloaded successfully")
        except Exception as exc:
            logger.error("[CACHE_INVALIDATION] Failed to reload application registry: %s", exc)


# ─── AI Providers & Credentials ───────────────────────────────────────────────

class AIService:
    def __init__(self, db: AsyncSession):
        self.db           = db
        self.provider_repo = AIProviderRepo(db)
        self.cred_repo    = AICredentialRepo(db)
        self.audit        = AuditLogRepo(db)

    # ─── Providers ───────────────────────────────────────────────────────────

    async def list_providers(self) -> list[dict]:
        providers = await self.provider_repo.list_all(enabled_only=False)
        result = []
        for p in providers:
            cred_count = await self.provider_repo.count_credentials(p.id)
            result.append(_provider_schema(p, credential_count=cred_count))
        return result

    async def get_provider(self, uid: str) -> dict:
        provider = await self.provider_repo.get_by_id(uid)
        if not provider:
            raise HTTPException(status_code=404, detail="AI provider not found.")
        cred_count = await self.provider_repo.count_credentials(uid)
        return _provider_schema(provider, credential_count=cred_count)

    async def create_provider(self, data: dict, admin_user_id: str | None = None) -> dict:
        # Validate uniqueness
        if await self.provider_repo.get_by_key(data.get("provider_key", "")):
            raise HTTPException(status_code=409, detail="provider_key must be unique.")
        if "name" in data:
            existing = await self.provider_repo.get_by_id(data["name"])
            # Check by querying all and comparing (no direct name lookup)
            for p in await self.provider_repo.list_all(enabled_only=False):
                if p.name == data["name"]:
                    raise HTTPException(status_code=409, detail="Provider name already exists.")
        provider = await self.provider_repo.create(data)
        await self.audit.record(action="ai_provider_created", admin_user_id=admin_user_id,
                                entity_type="ai_provider", entity_id=provider.id,
                                description=f"Created provider '{provider.name}'")
        return _provider_schema(provider, credential_count=0)

    async def update_provider(self, uid: str, data: dict, admin_user_id: str | None = None) -> dict:
        provider = await self.provider_repo.get_by_id(uid)
        if not provider:
            raise HTTPException(status_code=404, detail="AI provider not found.")
        # Check name uniqueness if being updated
        if "name" in data and data["name"] != provider.name:
            for p in await self.provider_repo.list_all(enabled_only=False):
                if p.name == data["name"] and p.id != uid:
                    raise HTTPException(status_code=409, detail="Provider name already exists.")
        # provider_key should be immutable (don't allow changes)
        data.pop("provider_key", None)
        updated = await self.provider_repo.update(uid, data)
        cred_count = await self.provider_repo.count_credentials(uid)
        await self.audit.record(action="ai_provider_updated", admin_user_id=admin_user_id,
                                entity_type="ai_provider", entity_id=uid)
        return _provider_schema(updated, credential_count=cred_count)

    async def delete_provider(self, uid: str, admin_user_id: str | None = None) -> bool:
        provider = await self.provider_repo.get_by_id(uid)
        if not provider:
            raise HTTPException(status_code=404, detail="AI provider not found.")
        ok = await self.provider_repo.delete(uid)
        await self.audit.record(action="ai_provider_deleted", admin_user_id=admin_user_id,
                                entity_type="ai_provider", entity_id=uid,
                                description=f"Deleted provider '{provider.name}'")
        return ok

    # ─── Credentials ──────────────────────────────────────────────────────────

    async def list_credentials(self) -> list[dict]:
        creds = await self.cred_repo.list_all()
        return [_credential_schema(c) for c in creds]

    async def get_credential(self, uid: str) -> dict:
        cred = await self.cred_repo.get_by_id(uid)
        if not cred:
            raise HTTPException(status_code=404, detail="Credential not found.")
        return _credential_schema(cred)

    async def create_credential(self, data: dict, admin_user_id: str | None = None) -> dict:
        provider = await self.provider_repo.get_by_id(data["provider_id"])
        if not provider:
            raise HTTPException(status_code=404, detail="AI provider not found.")
        # Encrypt API key before storing
        raw_key = data.pop("api_key", "")
        if not raw_key:
            raise HTTPException(status_code=422, detail="api_key is required.")
        data["api_key_encrypted"] = encrypt(raw_key)
        cred = await self.cred_repo.create(data)
        await self.audit.record(action="ai_configuration_created", admin_user_id=admin_user_id,
                                entity_type="ai_credential", entity_id=cred.id,
                                description=f"Created credential '{cred.name}' for {provider.name}")
        return _credential_schema(cred)

    async def update_credential(self, uid: str, data: dict, admin_user_id: str | None = None) -> dict:
        cred = await self.cred_repo.get_by_id(uid)
        if not cred:
            raise HTTPException(status_code=404, detail="Credential not found.")
        # Re-encrypt if key provided; otherwise leave encrypted key as-is
        raw_key = data.pop("api_key", None)
        if raw_key:
            data["api_key_encrypted"] = encrypt(raw_key)
        updated = await self.cred_repo.update(uid, data)
        # Invalidate AI config cache if the updated credential is active
        if updated and updated.is_active:
            from .ai_config import ai_config_manager
            ai_config_manager.invalidate()
        await self.audit.record(action="ai_configuration_updated", admin_user_id=admin_user_id,
                                entity_type="ai_credential", entity_id=uid)
        return _credential_schema(updated)

    async def delete_credential(self, uid: str, admin_user_id: str | None = None) -> bool:
        cred = await self.cred_repo.get_by_id(uid)
        if not cred:
            raise HTTPException(status_code=404, detail="Credential not found.")
        if cred.is_active:
            raise HTTPException(status_code=400, detail="Deactivate the credential before deleting it.")
        ok = await self.cred_repo.delete(uid)
        # Always invalidate cache on delete (belt and suspenders)
        from .ai_config import ai_config_manager
        ai_config_manager.invalidate()
        await self.audit.record(action="ai_configuration_deleted", admin_user_id=admin_user_id,
                                entity_type="ai_credential", entity_id=uid)
        return ok

    async def activate_credential(self, uid: str, admin_user_id: str | None = None) -> dict:
        cred = await self.cred_repo.get_by_id(uid)
        if not cred:
            raise HTTPException(status_code=404, detail="Credential not found.")
        activated = await self.cred_repo.activate(uid)
        # Sync active config to ai_config_manager so LLM factory picks it up immediately
        await self._sync_to_manager(activated)
        await self.audit.record(action="ai_configuration_activated", admin_user_id=admin_user_id,
                                entity_type="ai_credential", entity_id=uid,
                                description=f"Activated '{cred.name}'")
        return _credential_schema(activated)

    async def deactivate_credential(self, uid: str, admin_user_id: str | None = None) -> dict:
        cred = await self.cred_repo.get_by_id(uid)
        if not cred:
            raise HTTPException(status_code=404, detail="Credential not found.")
        if not cred.is_active:
            raise HTTPException(status_code=400, detail="Credential is already inactive.")
        deactivated = await self.cred_repo.deactivate(uid)
        from .ai_config import ai_config_manager
        ai_config_manager.invalidate()
        await self.audit.record(action="ai_configuration_deactivated", admin_user_id=admin_user_id,
                                entity_type="ai_credential", entity_id=uid,
                                description=f"Deactivated '{cred.name}'")
        return _credential_schema(deactivated)

    async def test_credential(self, uid: str, admin_user_id: str | None = None) -> dict:
        cred = await self.cred_repo.get_by_id(uid)
        if not cred:
            raise HTTPException(status_code=404, detail="Credential not found.")
        provider = await self.provider_repo.get_by_id(cred.provider_id)

        try:
            raw_key = decrypt(cred.api_key_encrypted) if cred.api_key_encrypted else ""
        except Exception:
            raw_key = ""

        success = False
        message = "Connection failed."
        if provider and provider.provider_key == "groq" and raw_key:
            try:
                import httpx
                resp = httpx.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {raw_key}"},
                    timeout=8,
                )
                success = resp.status_code == 200
                message = "Connection successful." if success else f"API returned {resp.status_code}."
            except Exception as e:
                message = f"Connection error: {type(e).__name__}"
        elif raw_key:
            success = True
            message = "Key present (live test not supported for this provider)."

        test_status = "success" if success else "failed"
        await self.cred_repo.record_test(uid, test_status)
        await self.audit.record(action="ai_configuration_tested", admin_user_id=admin_user_id,
                                entity_type="ai_credential", entity_id=uid,
                                description=f"Test result: {test_status}")
        return {"success": success, "message": message}

    async def _sync_to_manager(self, cred: AICredential) -> None:
        """Invalidate AIConfigManager cache so next request loads fresh DB config."""
        try:
            from .ai_config import ai_config_manager
            ai_config_manager.invalidate()
        except Exception:
            pass  # Don't fail the activation if manager sync fails


# ─── Logs ────────────────────────────────────────────────────────────────────

class LogService:
    def __init__(self, db: AsyncSession):
        self.db   = db
        self.repo = ApiRequestLogRepo(db)

    async def list_logs(self, *, limit: int = 200, application_id: str | None = None,
                        level: str | None = None) -> list[dict]:
        logs = await self.repo.list_recent(limit=limit, application_id=application_id, level=level)
        return [_log_schema(l) for l in logs]

    async def list_logs_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        application_id: str | None = None,
        level: str | None = None,
        status: str | None = None,
        method: str | None = None,
        source: str | None = None,
    ) -> dict:
        result = await self.repo.list_paginated(
            page=page,
            page_size=page_size,
            search=search,
            application_id=application_id,
            level=level,
            status=status,
            method=method,
            source=source,
        )
        return {
            "items": [_log_schema(l) for l in result["items"]],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
            "total_pages": result["total_pages"],
        }

    async def create_log(self, data: dict) -> None:
        await self.repo.create(data)


# ─── Global Settings ─────────────────────────────────────────────────────────

class SettingsService:
    def __init__(self, db: AsyncSession):
        self.db   = db
        self.repo = GlobalSettingRepo(db)

    async def get_all(self) -> dict:
        rows = await self.repo.get_all()
        return {r.setting_key: r.setting_value_json for r in rows}

    async def get(self, key: str) -> Any:
        row = await self.repo.get(key)
        return row.setting_value_json if row else None

    async def upsert(self, key: str, value: Any, updated_by: str | None = None) -> None:
        # Block secrets from being stored in settings
        _BLOCKED = {"api_key", "secret", "password", "token", "bearer"}
        if any(b in key.lower() for b in _BLOCKED):
            raise HTTPException(status_code=400, detail="Do not store secrets in global settings.")
        await self.repo.upsert(key, value, updated_by)

    async def update_many(self, settings: dict[str, Any], updated_by: str | None = None) -> dict:
        for k, v in settings.items():
            await self.upsert(k, v, updated_by)
        return await self.get_all()


# ─── Schema helpers (safe for frontend) ──────────────────────────────────────

def _user_schema(u: AdminUser) -> dict:
    return {
        "id": u.id, "email": u.email, "full_name": u.full_name,
        "role": u.role, "is_active": u.is_active,
        "avatar_url": u.avatar_url, "last_login_at": _iso(u.last_login_at),
        "created_at": _iso(u.created_at),
    }


def _app_schema(a, route_count: int | None = None) -> dict:
    return {
        "id": a.id, "name": a.name, "app_id": a.app_id,
        "description": a.description, "application_type": a.application_type,
        "category": a.category, "icon": a.icon, "base_url": a.base_url,
        "api_docs_url": a.api_docs_url, "status": a.status,
        "openapi_url": a.openapi_url, "discovery_mode": a.discovery_mode,
        "auth_type": a.auth_type, "is_enabled": a.is_enabled,
        "last_discovered_at": _iso(a.last_discovered_at),
        "last_health_check_at": _iso(a.last_health_check_at),
        "created_at": _iso(a.created_at), "updated_at": _iso(a.updated_at),
        "route_count": route_count,
    }


def _route_schema(r) -> dict:
    return {
        "id": r.id, "application_id": r.application_id,
        "method": r.method, "path": r.path, "operation_id": r.operation_id,
        "name": getattr(r, "name", None), "full_url": getattr(r, "full_url", None),
        "summary": r.summary, "description": r.description,
        "source": getattr(r, "source", "openapi"),
        "auth_required": r.auth_required, "auth_type": getattr(r, "auth_type", None),
        "status": r.status,
        "is_enabled": r.is_enabled, "last_discovered_at": _iso(r.last_discovered_at),
        "request_schema_json": r.request_schema_json,
        "response_schema_json": r.response_schema_json,
        "parameters_json": r.parameters_json,
        "headers_json": _mask_mapping(getattr(r, "headers_json", None)),
        "query_params_json": getattr(r, "query_params_json", None),
        "path_params_json": getattr(r, "path_params_json", None),
        "request_body_json": _mask_mapping(getattr(r, "request_body_json", None)),
        "content_type": getattr(r, "content_type", None),
        "created_at": _iso(r.created_at), "updated_at": _iso(r.updated_at),
    }


def _provider_schema(p, credential_count: int | None = None) -> dict:
    return {
        "id": p.id, "name": p.name, "provider_key": p.provider_key,
        "description": p.description, "icon": p.icon, "is_enabled": p.is_enabled,
        "credential_count": credential_count,
        "created_at": _iso(p.created_at), "updated_at": _iso(p.updated_at),
    }


def _credential_schema(c) -> dict:
    # NEVER return raw api_key_encrypted — only a masked hint
    masked = ""
    try:
        raw = decrypt(c.api_key_encrypted) if c.api_key_encrypted else ""
        masked = mask(raw)
    except Exception:
        masked = "************"
    return {
        "id": c.id, "provider_id": c.provider_id, "name": c.name,
        "model": c.model, "is_active": c.is_active,
        "api_key_masked": masked,
        "temperature": float(c.temperature) if c.temperature is not None else None,
        "max_tokens": c.max_tokens,
        "top_p": float(c.top_p) if c.top_p is not None else None,
        "last_tested_at": _iso(c.last_tested_at),
        "last_test_status": c.last_test_status,
        "created_at": _iso(c.created_at), "updated_at": _iso(c.updated_at),
    }


def _log_schema(l) -> dict:
    return {
        "id": l.id, "application_id": l.application_id,
        "conversation_id": l.conversation_id, "request_id": l.request_id,
        "method": l.method, "endpoint": l.endpoint, "source": l.source,
        "status_code": l.status_code, "status": l.status, "level": l.level,
        "message": l.message,
        "response_time_ms": float(l.response_time_ms) if l.response_time_ms else None,
        "error_code": l.error_code, "error_message": l.error_message,
        "created_at": _iso(l.created_at),
    }


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _normalize_discovery_mode(value: str | None, *, has_openapi: bool) -> str:
    aliases = {"dynamic": "dynamic_openapi", "static": "manual"}
    mode = aliases.get((value or "").strip(), (value or "").strip()) or ("hybrid" if has_openapi else "manual")
    if mode not in {"dynamic_openapi", "manual", "hybrid"}:
        raise HTTPException(status_code=422, detail="discovery_mode must be dynamic_openapi, manual, or hybrid.")
    if mode == "dynamic_openapi" and not has_openapi:
        raise HTTPException(status_code=422, detail="dynamic_openapi requires an openapi_url. Use manual when OpenAPI is unavailable.")
    return mode


def _manual_route_data(data: dict, *, partial: bool = False) -> dict:
    from .models import RouteStatus
    allowed = {
        "method", "path", "full_url", "operation_id", "name", "summary", "description",
        "auth_required", "auth_type", "status", "is_enabled", "request_schema_json",
        "response_schema_json", "parameters_json", "headers_json", "query_params_json",
        "path_params_json", "request_body_json", "content_type",
    }
    cleaned = {k: v for k, v in data.items() if k in allowed}
    if "method" in cleaned:
        cleaned["method"] = str(cleaned["method"]).upper()
    if not partial:
        cleaned.setdefault("source", "manual")
        cleaned.setdefault("status", "available")
        cleaned.setdefault("is_enabled", True)
        cleaned.setdefault("auth_required", False)
    else:
        cleaned["source"] = "manual"
    # Normalize status to canonical form
    if "status" in cleaned:
        cleaned["status"] = RouteStatus.normalize(cleaned["status"])
    path = cleaned.get("path")
    full_url = cleaned.get("full_url")
    if not partial or path is not None or full_url is not None:
        if not path and not full_url:
            raise HTTPException(status_code=422, detail="path or full_url is required.")
        if path and not str(path).startswith("/"):
            raise HTTPException(status_code=422, detail="path must start with '/'.")
    if "method" in cleaned and cleaned["method"] not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise HTTPException(status_code=422, detail="Unsupported HTTP method.")
    return cleaned


def _mask_mapping(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {k: ("********" if any(s in str(k).lower() for s in {"authorization", "api_key", "token", "secret", "password", "bearer"}) else v) for k, v in value.items()}


def _safe_headers(headers: dict) -> dict[str, str]:
    return {str(k): str(v) for k, v in headers.items() if not any(s in str(k).lower() for s in {"authorization", "api_key", "token", "secret", "password"})}


def _request_scoped_headers(headers: dict) -> dict[str, str]:
    blocked = {"host", "content-length", "connection", "transfer-encoding"}
    cleaned: dict[str, str] = {}
    for k, v in headers.items():
        key = str(k).strip()
        value = str(v).strip()
        if not key or not value or key.lower() in blocked:
            continue
        if key.lower() == "authorization":
            cleaned["Authorization"] = _normalize_authorization_value(value)
        else:
            cleaned[key] = value
    return cleaned


def _normalize_authorization_value(value: str) -> str:
    return value if value.lower().startswith("bearer ") else f"Bearer {value}"


def _has_header(headers: dict[str, str], name: str) -> bool:
    return any(key.lower() == name.lower() and bool(value.strip()) for key, value in headers.items())


def _param_values(params: Any) -> dict | None:
    if not isinstance(params, dict):
        return None
    return {k: (v.get("value") if isinstance(v, dict) else v) for k, v in params.items()}


def _display_headers(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if not any(s in k.lower() for s in {"authorization", "cookie", "token", "secret", "key"})}


def _safe_response(response: httpx.Response) -> Any:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:2000]
    return _mask_mapping(payload) if isinstance(payload, dict) else payload
