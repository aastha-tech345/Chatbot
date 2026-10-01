"""
Admin API router — all endpoints that back the Next.js admin frontend.

Mounted at /api/v1/admin/... in main.py.
All routes except /auth/login require a valid admin JWT.

SECURITY:
- No raw API keys are ever returned.
- Passwords are never echoed back.
- Auth headers are never logged.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, SecretStr, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .admin_auth import require_admin
from .services import (
    AuthService, ApplicationService, ApplicationRouteService,
    AIService, LogService, SettingsService,
)

router = APIRouter(prefix="/api/v1/admin")
ai_router = APIRouter(prefix="/api/v1/ai")


# ─────────────────────────────────────────────────────────────────────────────
#  Pydantic schemas  (request / response bodies)
# ─────────────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    refresh_token: str | None = None  # for logout / refresh

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)

class CreateAdminRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)

class ApplicationCreateRequest(BaseModel):
    service_key: SecretStr | None = None
    name: str = Field(min_length=1)
    app_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    description: str | None = None
    application_type: str = "web_application"
    category: str | None = None
    base_url: str = Field(min_length=1)
    api_docs_url: str | None = None
    openapi_url: str | None = None
    discovery_mode: str = "dynamic"
    status: str = "active"
    auth_type: str | None = None
    jwt_secret_env: str | None = None
    service_key_env: str | None = None

class ApplicationUpdateRequest(BaseModel):
    service_key: SecretStr | None = None
    name: str | None = None
    app_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]*$")
    description: str | None = None
    application_type: str | None = None
    category: str | None = None
    icon: str | None = None
    base_url: str | None = None
    api_docs_url: str | None = None
    openapi_url: str | None = None
    discovery_mode: str | None = None
    status: str | None = None
    auth_type: str | None = None
    is_enabled: bool | None = None

class AICredentialCreateRequest(BaseModel):
    provider_id: str
    name: str = Field(min_length=1)
    api_key: str = Field(min_length=1)   # plaintext — encrypted in service layer
    model: str = Field(min_length=1)
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None

class AICredentialUpdateRequest(BaseModel):
    name: str | None = None
    api_key: str | None = None           # optional re-key
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None

class AIProviderCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    provider_key: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    description: str | None = None
    icon: str | None = None
    is_enabled: bool = True

class AIProviderUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    is_enabled: bool | None = None

class RouteStatusRequest(BaseModel):
    is_enabled: bool

class ManualRouteRequest(BaseModel):
    method: str = Field(min_length=1)
    path: str | None = None
    full_url: str | None = None
    operation_id: str | None = None
    name: str | None = None
    summary: str | None = None
    description: str | None = None
    auth_required: bool = False
    auth_type: str | None = None
    status: str = "available"
    is_enabled: bool = True
    request_schema_json: dict[str, Any] | None = None
    response_schema_json: dict[str, Any] | None = None
    parameters_json: dict[str, Any] | None = None
    headers_json: dict[str, Any] | None = None
    query_params_json: dict[str, Any] | None = None
    path_params_json: dict[str, Any] | None = None
    request_body_json: dict[str, Any] | None = None
    content_type: str | None = None

    @model_validator(mode="after")
    def normalize_status(self):
        from .models import RouteStatus
        self.status = RouteStatus.normalize(self.status)
        return self

class ManualRouteUpdateRequest(BaseModel):
    method: str | None = None
    path: str | None = None
    full_url: str | None = None
    operation_id: str | None = None
    name: str | None = None
    summary: str | None = None
    description: str | None = None
    auth_required: bool | None = None
    auth_type: str | None = None
    status: str | None = None
    is_enabled: bool | None = None
    request_schema_json: dict[str, Any] | None = None
    response_schema_json: dict[str, Any] | None = None
    parameters_json: dict[str, Any] | None = None
    headers_json: dict[str, Any] | None = None
    query_params_json: dict[str, Any] | None = None
    path_params_json: dict[str, Any] | None = None
    request_body_json: dict[str, Any] | None = None
    content_type: str | None = None

    @model_validator(mode="after")
    def normalize_status(self):
        if self.status:
            from .models import RouteStatus
            self.status = RouteStatus.normalize(self.status)
        return self

class SettingsUpdateRequest(BaseModel):
    settings: dict[str, Any]

class RouteTestRequest(BaseModel):
    method: str | None = None
    headers: dict[str, Any] | None = None
    query_params: dict[str, Any] | None = None
    body: Any = None


# ─────────────────────────────────────────────────────────────────────────────
#  Auth
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/auth/login", tags=["auth"])
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    svc = AuthService(db)
    return await svc.login(body.email, body.password, request)


@router.post("/auth/logout", tags=["auth"])
async def logout(body: LogoutRequest, admin_id: str = Depends(require_admin),
                 db: AsyncSession = Depends(get_db)):
    await AuthService(db).logout(body.refresh_token, admin_id)
    return {"success": True}


@router.post("/auth/refresh", tags=["auth"])
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).refresh(body.refresh_token)


@router.get("/auth/me", tags=["auth"])
async def me(admin_id: str = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await AuthService(db).me(admin_id)


@router.put("/auth/password", tags=["auth"])
async def change_password(body: ChangePasswordRequest,
                          admin_id: str = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    return await AuthService(db).change_password(admin_id, body.current_password, body.new_password)


@router.post("/auth/setup", tags=["auth"])
async def setup_first_admin(body: CreateAdminRequest, db: AsyncSession = Depends(get_db)):
    """
    One-time endpoint to create the first admin user.
    Disabled once any admin exists — returns 409.
    """
    svc = AuthService(db)
    if await svc.has_any_admin():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Admin already exists. Use the login endpoint.",
        )
    return await svc.create_admin(email=body.email, password=body.password, full_name=body.full_name)


# ─────────────────────────────────────────────────────────────────────────────
#  Applications
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/applications", tags=["applications"])
async def list_applications(
    page: int = 1,
    page_size: int = 10,
    search: str | None = None,
    status: str | None = None,
    application_type: str | None = None,
    category: str | None = None,
    is_enabled: bool | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    admin_id: str = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List applications with server-side pagination, search, filtering, and sorting."""
    result = await ApplicationService(db).list_paginated(
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
    return result


@router.get("/applications/{app_uid}", tags=["applications"])
async def get_application(app_uid: str, admin_id: str = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    return await ApplicationService(db).get(app_uid)


@router.post("/applications", tags=["applications"], status_code=201)
async def create_application(body: ApplicationCreateRequest,
                             admin_id: str = Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    if not data.get("openapi_url") and data.get("api_docs_url", "").endswith(".json"):
        data["openapi_url"] = data["api_docs_url"]
    return await ApplicationService(db).create(data, admin_id)


@router.put("/applications/{app_uid}", tags=["applications"])
async def update_application(app_uid: str, body: ApplicationUpdateRequest,
                             admin_id: str = Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    data = body.model_dump(exclude_none=True)
    if not data.get("openapi_url") and data.get("api_docs_url", "").endswith(".json"):
        data["openapi_url"] = data["api_docs_url"]
    return await ApplicationService(db).update(app_uid, data, admin_id)


@router.delete("/applications/{app_uid}", tags=["applications"])
async def delete_application(app_uid: str, admin_id: str = Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    await ApplicationService(db).delete(app_uid, admin_id)
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────────────
#  Application Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/applications/{app_uid}/routes", tags=["routes"])
async def list_app_routes(app_uid: str, page: int | None = None, page_size: int | None = None,
                          q: str | None = None, method: str | None = None, status: str | None = None,
                          admin_id: str = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    route_svc = ApplicationRouteService(db)
    if page is not None or page_size is not None or q or method or status:
        return await route_svc.list_for_app_paginated(
            app_uid,
            page or 1,
            page_size or 25,
            search=q,
            method=method,
            status=status,
        )
    return await route_svc.list_for_app(app_uid)


@router.post("/applications/{app_uid}/discover", tags=["routes"])
async def discover_routes(app_uid: str, admin_id: str = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    """
    Trigger OpenAPI discovery for an application and persist the results.
    The live openapi_discovery module remains the source of truth.
    """
    from .repositories import ApplicationRepo
    app_repo = ApplicationRepo(db)
    app = await app_repo.get_by_id(app_uid)
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    if not app.openapi_url:
        raise HTTPException(status_code=400, detail="Application has no openapi_url configured. Use manual API registration instead.")

    from .openapi_discovery import discover_openapi_routes
    from .app_registry import application_registry
    from datetime import datetime, timezone
    try:
        routes = await discover_openapi_routes(app.app_id, app.base_url, app.openapi_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenAPI discovery failed: {exc}")

    route_svc = ApplicationRouteService(db)
    route_dicts = [
        {
            "method":        r.method.value,
            "path":          r.path,
            "operation_id":  r.name,
            "summary":       r.description,
            "description":   r.description,
            "auth_required": r.requires_auth,
            "status":        "available",
            "is_enabled":    True,
            "parameters_json": r.parameters,
            "source": "openapi",
            "last_discovered_at": datetime.now(timezone.utc),
        }
        for r in routes
    ]
    count = await route_svc.persist_discovered_routes(app_uid, route_dicts)
    try:
        application_registry.update_routes(app.app_id, routes)
    except HTTPException:
        # Admin-created apps can exist before they are registered in the runtime
        # config. The admin route cache is still the source for this page.
        pass
    refreshed_routes = await route_svc.list_for_app(app_uid)
    return {"discovered": count, "app_uid": app_uid, "routes": refreshed_routes}


@router.post("/applications/{app_uid}/routes", tags=["routes"], status_code=201)
async def create_manual_route(app_uid: str, body: ManualRouteRequest,
                              admin_id: str = Depends(require_admin),
                              db: AsyncSession = Depends(get_db)):
    return await ApplicationRouteService(db).create_manual_route(app_uid, body.model_dump(exclude_none=True), admin_id)


@router.put("/routes/{route_id}", tags=["routes"])
async def update_manual_route(route_id: str, body: ManualRouteUpdateRequest,
                              admin_id: str = Depends(require_admin),
                              db: AsyncSession = Depends(get_db)):
    return await ApplicationRouteService(db).update_manual_route(route_id, body.model_dump(exclude_none=True), admin_id)


@router.delete("/routes/{route_id}", tags=["routes"])
async def delete_manual_route(route_id: str, admin_id: str = Depends(require_admin),
                              db: AsyncSession = Depends(get_db)):
    await ApplicationRouteService(db).delete_manual_route(route_id, admin_id)
    return {"success": True}


@router.post("/routes/{route_id}/test", tags=["routes"])
async def test_manual_route(route_id: str, request: Request, body: RouteTestRequest | None = None,
                            admin_id: str = Depends(require_admin),
                            db: AsyncSession = Depends(get_db)):
    payload = body.model_dump(exclude_none=True) if body else {}
    test_authorization = request.headers.get("x-api-test-authorization")
    if test_authorization:
        payload_headers = dict(payload.get("headers") or {})
        payload_headers["Authorization"] = test_authorization
        payload["headers"] = payload_headers
    return await ApplicationRouteService(db).test_route(route_id, admin_id, **payload)


@router.put("/routes/{route_id}/status", tags=["routes"])
async def update_route_status(route_id: str, body: RouteStatusRequest,
                              admin_id: str = Depends(require_admin),
                              db: AsyncSession = Depends(get_db)):
    await ApplicationRouteService(db).update_route_status(route_id, body.is_enabled, admin_id)
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────────────
#  AI Providers & Credentials
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/ai/providers", tags=["ai"])
async def list_ai_providers(admin_id: str = Depends(require_admin),
                            db: AsyncSession = Depends(get_db)):
    return await AIService(db).list_providers()


@router.get("/ai/providers/{provider_id}", tags=["ai"])
async def get_ai_provider(provider_id: str, admin_id: str = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    return await AIService(db).get_provider(provider_id)


@router.post("/ai/providers", tags=["ai"], status_code=201)
async def create_ai_provider(body: AIProviderCreateRequest,
                             admin_id: str = Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    data = body.model_dump()
    return await AIService(db).create_provider(data, admin_id)


@router.put("/ai/providers/{provider_id}", tags=["ai"])
async def update_ai_provider(provider_id: str, body: AIProviderUpdateRequest,
                             admin_id: str = Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    return await AIService(db).update_provider(provider_id, body.model_dump(exclude_none=True), admin_id)


@router.delete("/ai/providers/{provider_id}", tags=["ai"])
async def delete_ai_provider(provider_id: str, admin_id: str = Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    await AIService(db).delete_provider(provider_id, admin_id)
    return {"success": True}


@router.get("/ai/credentials", tags=["ai"])
async def list_ai_credentials(admin_id: str = Depends(require_admin),
                              db: AsyncSession = Depends(get_db)):
    return await AIService(db).list_credentials()


@router.get("/ai/credentials/{cred_id}", tags=["ai"])
async def get_ai_credential(cred_id: str, admin_id: str = Depends(require_admin),
                            db: AsyncSession = Depends(get_db)):
    return await AIService(db).get_credential(cred_id)


@router.post("/ai/credentials", tags=["ai"], status_code=201)
async def create_ai_credential(body: AICredentialCreateRequest,
                               admin_id: str = Depends(require_admin),
                               db: AsyncSession = Depends(get_db)):
    data = body.model_dump()
    return await AIService(db).create_credential(data, admin_id)


@router.put("/ai/credentials/{cred_id}", tags=["ai"])
async def update_ai_credential(cred_id: str, body: AICredentialUpdateRequest,
                               admin_id: str = Depends(require_admin),
                               db: AsyncSession = Depends(get_db)):
    return await AIService(db).update_credential(cred_id, body.model_dump(exclude_none=True), admin_id)


@router.delete("/ai/credentials/{cred_id}", tags=["ai"])
async def delete_ai_credential(cred_id: str, admin_id: str = Depends(require_admin),
                               db: AsyncSession = Depends(get_db)):
    await AIService(db).delete_credential(cred_id, admin_id)
    return {"success": True}


@router.post("/ai/credentials/{cred_id}/activate", tags=["ai"])
async def activate_ai_credential(cred_id: str, admin_id: str = Depends(require_admin),
                                 db: AsyncSession = Depends(get_db)):
    return await AIService(db).activate_credential(cred_id, admin_id)


@router.post("/ai/credentials/{cred_id}/deactivate", tags=["ai"])
async def deactivate_ai_credential(cred_id: str, admin_id: str = Depends(require_admin),
                                   db: AsyncSession = Depends(get_db)):
    return await AIService(db).deactivate_credential(cred_id, admin_id)


@router.post("/ai/credentials/{cred_id}/test", tags=["ai"])
async def test_ai_credential(cred_id: str, admin_id: str = Depends(require_admin),
                             db: AsyncSession = Depends(get_db)):
    return await AIService(db).test_credential(cred_id, admin_id)


# Public path aliases for the admin frontend's AI provider/configuration module.
# They reuse AICredential as the configuration entity and keep the same admin JWT guard.
@ai_router.get("/providers", tags=["ai"])
async def list_ai_providers_alias(admin_id: str = Depends(require_admin),
                                  db: AsyncSession = Depends(get_db)):
    return await AIService(db).list_providers()


@ai_router.get("/providers/{provider_id}", tags=["ai"])
async def get_ai_provider_alias(provider_id: str, admin_id: str = Depends(require_admin),
                                db: AsyncSession = Depends(get_db)):
    return await AIService(db).get_provider(provider_id)


@ai_router.post("/providers", tags=["ai"], status_code=201)
async def create_ai_provider_alias(body: AIProviderCreateRequest,
                                   admin_id: str = Depends(require_admin),
                                   db: AsyncSession = Depends(get_db)):
    return await AIService(db).create_provider(body.model_dump(), admin_id)


@ai_router.put("/providers/{provider_id}", tags=["ai"])
@ai_router.patch("/providers/{provider_id}", tags=["ai"])
async def update_ai_provider_alias(provider_id: str, body: AIProviderUpdateRequest,
                                   admin_id: str = Depends(require_admin),
                                   db: AsyncSession = Depends(get_db)):
    return await AIService(db).update_provider(provider_id, body.model_dump(exclude_none=True), admin_id)


@ai_router.delete("/providers/{provider_id}", tags=["ai"])
async def delete_ai_provider_alias(provider_id: str, admin_id: str = Depends(require_admin),
                                   db: AsyncSession = Depends(get_db)):
    await AIService(db).delete_provider(provider_id, admin_id)
    return {"success": True}


@ai_router.get("/configurations", tags=["ai"])
async def list_ai_configurations_alias(admin_id: str = Depends(require_admin),
                                       db: AsyncSession = Depends(get_db)):
    return await AIService(db).list_credentials()


@ai_router.get("/configurations/{config_id}", tags=["ai"])
async def get_ai_configuration_alias(config_id: str, admin_id: str = Depends(require_admin),
                                     db: AsyncSession = Depends(get_db)):
    return await AIService(db).get_credential(config_id)


@ai_router.post("/configurations", tags=["ai"], status_code=201)
async def create_ai_configuration_alias(body: AICredentialCreateRequest,
                                        admin_id: str = Depends(require_admin),
                                        db: AsyncSession = Depends(get_db)):
    return await AIService(db).create_credential(body.model_dump(), admin_id)


@ai_router.put("/configurations/{config_id}", tags=["ai"])
@ai_router.patch("/configurations/{config_id}", tags=["ai"])
async def update_ai_configuration_alias(config_id: str, body: AICredentialUpdateRequest,
                                        admin_id: str = Depends(require_admin),
                                        db: AsyncSession = Depends(get_db)):
    return await AIService(db).update_credential(config_id, body.model_dump(exclude_none=True), admin_id)


@ai_router.delete("/configurations/{config_id}", tags=["ai"])
async def delete_ai_configuration_alias(config_id: str, admin_id: str = Depends(require_admin),
                                        db: AsyncSession = Depends(get_db)):
    await AIService(db).delete_credential(config_id, admin_id)
    return {"success": True}


@ai_router.post("/configurations/{config_id}/activate", tags=["ai"])
async def activate_ai_configuration_alias(config_id: str, admin_id: str = Depends(require_admin),
                                          db: AsyncSession = Depends(get_db)):
    return await AIService(db).activate_credential(config_id, admin_id)


@ai_router.post("/configurations/{config_id}/deactivate", tags=["ai"])
async def deactivate_ai_configuration_alias(config_id: str, admin_id: str = Depends(require_admin),
                                            db: AsyncSession = Depends(get_db)):
    return await AIService(db).deactivate_credential(config_id, admin_id)


@ai_router.post("/configurations/{config_id}/test", tags=["ai"])
async def test_ai_configuration_alias(config_id: str, admin_id: str = Depends(require_admin),
                                      db: AsyncSession = Depends(get_db)):
    return await AIService(db).test_credential(config_id, admin_id)


# ─────────────────────────────────────────────────────────────────────────────
#  Logs
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/logs", tags=["logs"])
async def list_logs(
    page: int = 1,
    page_size: int = 25,
    search: str | None = None,
    application_id: str | None = None,
    level: str | None = None,
    status: str | None = None,
    method: str | None = None,
    source: str | None = None,
    admin_id: str = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await LogService(db).list_logs_paginated(
        page=page,
        page_size=page_size,
        search=search,
        application_id=application_id,
        level=level,
        status=status,
        method=method,
        source=source,
    )


@router.get("/applications/{app_uid}/logs", tags=["logs"])
async def list_app_logs(app_uid: str, limit: int = 100, level: str | None = None,
                        admin_id: str = Depends(require_admin),
                        db: AsyncSession = Depends(get_db)):
    return await LogService(db).list_logs(limit=limit, application_id=app_uid, level=level)


# ─────────────────────────────────────────────────────────────────────────────
#  Settings
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/settings", tags=["settings"])
async def get_settings(admin_id: str = Depends(require_admin),
                       db: AsyncSession = Depends(get_db)):
    return await SettingsService(db).get_all()


@router.put("/settings", tags=["settings"])
async def update_settings(body: SettingsUpdateRequest,
                          admin_id: str = Depends(require_admin),
                          db: AsyncSession = Depends(get_db)):
    return await SettingsService(db).update_many(body.settings, updated_by=admin_id)
