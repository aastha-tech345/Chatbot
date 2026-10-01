from __future__ import annotations

import hmac
import logging
import os
import json
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4, uuid5, NAMESPACE_URL

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ai_config import ai_config_manager
from .authorization import authenticate, normalize_authorization, user_authorization
from .sanitization import safe_data, safe_text
from .conversations import conversations
from .api_client import ApplicationAPIClient
from .app_registry import application_registry
from .models import ApplicationDefinition, RouteDefinition
from .planner import RoutePlanner
from .security import verify_hs256_jwt
from .workflow import ChatWorkflow
from .database import create_tables
from .admin_routes import ai_router, router as admin_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FRONTEND_DIST_DIR = Path(__file__).resolve().parents[1] / "frontend_dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler for async startup and shutdown."""
    # Startup
    logger.info("[STARTUP] Initializing database tables")
    await create_tables()
    logger.info("[STARTUP] Database tables ready")
    logger.info("[STARTUP] Initializing application registry")
    await application_registry.initialize()
    logger.info("[STARTUP] Application registry initialized")
    yield
    # Shutdown
    logger.info("[SHUTDOWN] Shutting down application registry")


app = FastAPI(title="Master Chatbot", version="1.0.0", lifespan=lifespan)
workflow = ChatWorkflow(application_registry, RoutePlanner(), ApplicationAPIClient())

# ── CORS (allow Next.js frontend) ───────────────────────────────────────────
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Admin API router ─────────────────────────────────────────────────────────
app.include_router(admin_router)
app.include_router(ai_router)


def _request_field_names(body: object) -> list[str]:
    return sorted(body.keys()) if isinstance(body, dict) else []


@app.exception_handler(RequestValidationError)
async def request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Validation already consumed the request stream. Re-reading it can hang.
    # Use only field names below; never log or return body values (including secrets).
    body: object = exc.body
    errors = [
        {
            "loc": error.get("loc", []),
            "type": error.get("type", ""),
            "msg": error.get("msg", ""),
        }
        for error in exc.errors()
    ]
    logger.warning(
        "[CHAT] request validation failed path=%s status=422 fields=%s errors=%s",
        request.url.path,
        _request_field_names(body),
        errors,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(exc.errors())},
    )


class ChatRequest(BaseModel):
    app_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)


class ChatResponse(BaseModel):
    success: bool = True
    app_id: str
    message: str
    data: list[dict]
    intent: str | None = None
    conversation_id: str
    session_id: str
    request_id: str
    metadata: dict[str, object]


class ApplicationRegistrationRequest(ApplicationDefinition):
    """An application contract submitted by the SDK registration CLI."""

    app_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    jwt_secret_env: str = ""
    jwt_algorithm: str = "HS256"
    service_key_env: str = Field(min_length=1)
    openapi_url: str | None = None
    discovery_mode: str = "static"
    routes: list[RouteDefinition] = Field(default_factory=list)

    def application(self) -> ApplicationDefinition:
        return ApplicationDefinition.model_validate(self.model_dump())


class RouteSyncRequest(BaseModel):
    routes: list[RouteDefinition] = Field(min_length=1)


class AIConfigRequest(BaseModel):
    ai_provider: str
    groq_api_key: str
    groq_model: str


def _require_registration_key(
    registration_key: str | None = Header(
        default=None,
        alias="X-Master-Chatbot-Registration-Key",
    ),
) -> None:
    configured_key = os.getenv("MASTER_CHATBOT_REGISTRATION_KEY", "")
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application registration is not configured",
        )
    if not registration_key or not hmac.compare_digest(registration_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Application registration is not authorized",
        )


def _require_config_key(
    config_key: str | None = Header(default=None, alias="X-Master-Chatbot-Config-Key"),
) -> None:
    configured_key = os.getenv("MASTER_CHATBOT_CONFIG_KEY", "") or os.getenv("MASTER_CHATBOT_REGISTRATION_KEY", "")
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI configuration management is not configured",
        )
    if not config_key or not hmac.compare_digest(config_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI configuration management is not authorized",
        )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "master-chatbot"}


@app.get("/api/v1/health/{app_id}")
async def application_health(app_id: str) -> dict[str, object]:
    try:
        application = await application_registry.get_fresh(app_id)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_400_BAD_REQUEST:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"status": "unhealthy", "app_id": app_id, "registered": False},
            )
        raise

    route_count = len(application.routes)
    base_url_configured = bool(application.base_url)
    chatbot_enabled = bool(application.chatbot.enabled)
    return {
        "status": "healthy",
        "service": "master-chatbot",
        "app_id": application.app_id,
        "registered": True,
        "chatbot_enabled": chatbot_enabled,
        "base_url_configured": base_url_configured,
        "route_count": route_count,
        "chat_ready": chatbot_enabled and base_url_configured and route_count > 0,
    }


@app.get("/api/v1/config/ai")
async def get_ai_config(_: None = Depends(_require_config_key)) -> dict[str, object]:
    try:
        config = await ai_config_manager.get_active()
        return {
            "ai_provider": config.provider_key,
            "groq_api_key_configured": bool(config.api_key),
            "groq_api_key_masked": config.api_key_masked,
            "groq_model": config.model,
        }
    except Exception:
        return {"ai_provider": "", "groq_api_key_configured": False, "groq_api_key_masked": "", "groq_model": ""}


@app.put("/api/v1/config/ai")
async def update_ai_config(payload: AIConfigRequest, _: None = Depends(_require_config_key)) -> dict[str, object]:
    # Legacy endpoint — invalidate cache so next request picks up DB changes
    ai_config_manager.invalidate()
    logger.info("[CONFIG] AI cache invalidated via legacy endpoint")
    return {"message": "Use the Admin panel to update AI configuration. Cache has been invalidated."}


@app.post("/api/v1/registry/applications/register")
async def register_application(
    payload: ApplicationRegistrationRequest,
    _: None = Depends(_require_registration_key),
) -> dict[str, object]:
    """Register an application via SDK. Persists to DB and updates in-memory registry."""
    from .database import AsyncSessionLocal
    from .repositories import ApplicationRepo
    application = payload.application()
    async with AsyncSessionLocal() as db:
        repo = ApplicationRepo(db)
        existing = await repo.get_by_app_id(application.app_id)
        app_data = {
            "app_id": application.app_id,
            "name": application.name,
            "base_url": application.base_url,
            "openapi_url": application.openapi_url,
            "discovery_mode": application.discovery_mode,
            "jwt_algorithm": application.jwt_algorithm,
            "auth_config_json": application.authentication.model_dump(),
            "chatbot_config_json": application.chatbot.model_dump(),
            "is_enabled": True,
            "status": "active",
        }
        if existing:
            await repo.update(existing.id, app_data)
        else:
            await repo.create(app_data)
        await db.commit()
    # Reload registry from DB
    await application_registry.reload()
    application_registry.upsert(application)
    logger.info("[REGISTRY] application registered app_id=%s route_count=%s", application.app_id, len(application.routes))
    return application_registry.status(application.app_id)


@app.put("/api/v1/registry/applications/{app_id}/routes")
async def sync_application_routes(
    app_id: str,
    payload: RouteSyncRequest,
    _: None = Depends(_require_registration_key),
) -> dict[str, object]:
    application = application_registry.update_routes(app_id, payload.routes)
    logger.info("[REGISTRY] application routes synchronized app_id=%s route_count=%s", application.app_id, len(application.routes))
    return application_registry.status(app_id)


@app.get("/api/v1/registry/applications/{app_id}")
async def application_status(
    app_id: str,
    _: None = Depends(_require_registration_key),
) -> dict[str, object]:
    return application_registry.status(app_id)


@app.delete("/api/v1/registry/applications/{app_id}")
async def unregister_application(
    app_id: str,
    _: None = Depends(_require_registration_key),
) -> dict[str, bool]:
    application_registry.unregister(app_id)
    logger.info("[REGISTRY] application unregistered app_id=%s", app_id)
    return {"success": True}


def _require_app_service(application: ApplicationDefinition, service_key: str | None) -> None:
    """Validate the service key from DB credentials."""
    configured = application_registry.get_service_key(application.app_id)
    if not configured or not service_key or not hmac.compare_digest(configured, service_key):
        raise HTTPException(status_code=403, detail="Application service is not authorized")


@app.get("/api/v1/registry/applications/{app_id}/config")
async def app_config(app_id: str, service_key: str | None = Header(default=None, alias="X-Master-Chatbot-Service-Key")) -> dict:
    application = application_registry.get(app_id)
    _require_app_service(application, service_key)
    return application.public_config()


@app.get("/api/v1/registry/applications/{app_id}/auth-config")
async def auth_config(app_id: str, service_key: str | None = Header(default=None, alias="X-Master-Chatbot-Service-Key")) -> dict:
    config = await app_config(app_id, service_key)
    return {"app_id": app_id, **config["authentication"]}


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, authorization: str | None = Header(default=None), service_key: str | None = Header(default=None, alias="X-Master-Chatbot-Service-Key")) -> ChatResponse:
    request_id = payload.request_id or request.headers.get("X-Request-Id") or str(uuid4())
    session_id = payload.session_id or request.headers.get("X-Chat-Session-Id") or str(uuid4())
    conversation_id = payload.conversation_id or str(uuid4())
    logger.info("[CHAT] request received app_id=%s request_id=%s", payload.app_id, request_id)
    # Admin updates can land on another worker; refresh before planning or auth.
    application = await application_registry.get_fresh(payload.app_id)
    _require_app_service(application, service_key)
    if not application.base_url:
        raise HTTPException(status_code=503, detail="Application integration is not configured")
    if not application.chatbot.enabled:
        raise HTTPException(status_code=403, detail="Chatbot is disabled for this application")
    authorization = normalize_authorization(authorization)
    auth_state = await authenticate(application, authorization, verifier=verify_hs256_jwt)
    principal = f"user:{auth_state.user_id}:roles:{','.join(sorted(auth_state.roles))}" if auth_state.authenticated else f"guest:{session_id}"
    if not payload.conversation_id:
        conversation_id = str(uuid5(NAMESPACE_URL, f"{payload.app_id}:{principal}:{session_id}"))
    conversation = conversations.get(payload.app_id, str(principal), conversation_id)
    async with conversation.lock:
        if auth_state.authenticated and not conversation.turns:
            guest = conversations.entries.get((payload.app_id, f"guest:{session_id}", conversation_id))
            if guest:
                conversation.turns = list(guest.turns)
        cached = conversation.responses.get(request_id)
        if cached:
            if cached[0] != payload.message:
                raise HTTPException(status_code=409, detail="Request ID already used for another message.")
            return cached[1]
        auth_context = user_authorization.set(authorization if auth_state.authenticated else None)
        try:
            result = await workflow.run({"application": application, "message": safe_text(payload.message), "auth_state": auth_state, "request_id": request_id, "history": conversation.turns, "checkout_context": conversation.checkout_context})
        except HTTPException as exc:
            logger.exception(
                "[CHAT] workflow_http_exception app_id=%s request_id=%s exc_type=%s status_code=%s message=%s",
                payload.app_id,
                request_id,
                type(exc).__name__,
                exc.status_code,
                exc.detail,
            )
            raise
        except Exception as exc:
            logger.exception(
                "[CHAT] workflow_unhandled_exception app_id=%s request_id=%s exc_type=%s message=%s",
                payload.app_id,
                request_id,
                type(exc).__name__,
                exc,
            )
            raise
        finally:
            user_authorization.reset(auth_context)
        logger.info(
            "[CHAT] workflow_result app_id=%s request_id=%s keys=%s response_message=%s data_type=%s metadata=%s",
            payload.app_id,
            request_id,
            sorted(result.keys()),
            safe_text(str(result.get("response_message", "")))[:1000],
            type(result.get("data", [])).__name__,
            safe_text(json.dumps(result.get("metadata", {}), default=str))[:4000],
        )
        try:
            result["metadata"]["app_config"] = application.public_config()
            logger.info(
                "[CHAT] api_response_normalization_ok app_id=%s request_id=%s data_type=%s data_len=%s metadata_keys=%s",
                payload.app_id,
                request_id,
                type(result.get("data", [])).__name__,
                len(result.get("data", [])) if isinstance(result.get("data", []), list) else "n/a",
                sorted(result["metadata"].keys()),
            )
        except Exception as exc:
            logger.exception(
                "[CHAT] api_response_normalization_failed app_id=%s request_id=%s exc_type=%s message=%s result=%s",
                payload.app_id,
                request_id,
                type(exc).__name__,
                exc,
                safe_text(json.dumps(result, default=str))[:4000],
            )
            raise
        try:
            response = ChatResponse(app_id=payload.app_id, message=result["response_message"], data=result.get("data", []), intent=result["metadata"].get("route"), conversation_id=conversation_id, session_id=session_id, request_id=request_id, metadata=result["metadata"])
            logger.info(
                "[CHAT] chat_response_created app_id=%s request_id=%s route=%s data_len=%d",
                payload.app_id,
                request_id,
                result["metadata"].get("route"),
                len(response.data),
            )
        except Exception as exc:
            logger.exception(
                "[CHAT] chat_response_creation_failed app_id=%s request_id=%s exc_type=%s message=%s result=%s",
                payload.app_id,
                request_id,
                type(exc).__name__,
                exc,
                safe_text(json.dumps(result, default=str))[:4000],
            )
            raise
        conversation.checkout_context = result.get("checkout_context", conversation.checkout_context)
        if result.get("metadata", {}).get("has_checkout_link"):
            conversation.checkout_context = {}
        # Keep recent API identifiers for follow-up actions; bound retained payload sizes.
        context_data = json.dumps(safe_data(result.get("data", [])), default=str)
        conversation.turns.extend([
            {"role": "user", "content": safe_text(payload.message)},
            {"role": "assistant", "content": result["response_message"], "data": context_data[:24000]},
        ])
        conversation.turns = conversation.turns[-8:]
        conversation.responses[request_id] = (payload.message, response)
        while len(conversation.responses) > 20:
            conversation.responses.popitem(last=False)
    metadata = result["metadata"]
    logger.info("[CHAT] response generated app_id=%s route=%s request_id=%s", payload.app_id, metadata.get("route"), request_id)
    return response


next_static_dir = FRONTEND_DIST_DIR / "_next"
if next_static_dir.is_dir():
    app.mount("/_next", StaticFiles(directory=next_static_dir), name="next-static")


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
async def serve_frontend(full_path: str) -> FileResponse:
    if full_path.startswith(("api/", "docs", "redoc")) or full_path == "openapi.json":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )

    if not FRONTEND_DIST_DIR.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frontend build not found",
        )

    dist_root = FRONTEND_DIST_DIR.resolve()
    requested_path = (FRONTEND_DIST_DIR / full_path).resolve()

    requested_candidates = [requested_path]
    if requested_path.suffix == "":
        requested_candidates.append(requested_path.with_suffix(".html"))
    requested_candidates.append(requested_path / "index.html")

    # Static export generates dynamic app pages only for this placeholder ID.
    # Resolve real IDs to that shell so the client can hydrate using the URL's
    # actual ID and load its data from the API.
    placeholder_path = full_path
    app_registry_prefix = "app-registry/"
    if placeholder_path.startswith(app_registry_prefix):
        path_parts = placeholder_path.split("/")
        if len(path_parts) >= 2 and path_parts[1] not in {"new", ""}:
            path_parts[1] = "__static_export_placeholder__"
            placeholder_path = "/".join(path_parts)

    placeholder_requested = (FRONTEND_DIST_DIR / placeholder_path).resolve()
    placeholder_candidates = [placeholder_requested]
    if placeholder_requested.suffix == "":
        placeholder_candidates.append(placeholder_requested.with_suffix(".html"))
    placeholder_candidates.append(placeholder_requested / "index.html")

    candidates = requested_candidates + placeholder_candidates

    for candidate in candidates:
        candidate = candidate.resolve()

        if candidate.is_file() and (
            candidate == dist_root or dist_root in candidate.parents
        ):
            return FileResponse(candidate)

    index_path = FRONTEND_DIST_DIR / "index.html"

    if not index_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frontend build not found",
        )

    return FileResponse(index_path)