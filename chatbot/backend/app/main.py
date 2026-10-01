from __future__ import annotations

import hmac
import logging
import os
from uuid import uuid4, uuid5, NAMESPACE_URL

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .authorization import authenticate
from .sanitization import safe_data, safe_text
from .conversations import conversations
from .api_client import ApplicationAPIClient
from .app_registry import application_registry
from .models import ApplicationDefinition, RouteDefinition
from .planner import RoutePlanner
from .security import verify_hs256_jwt
from .workflow import ChatWorkflow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
app = FastAPI(title="Master Chatbot", version="1.0.0")
workflow = ChatWorkflow(application_registry, RoutePlanner(), ApplicationAPIClient())


def _request_field_names(body: object) -> list[str]:
    return sorted(body.keys()) if isinstance(body, dict) else []


@app.exception_handler(RequestValidationError)
async def request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    body: object = None
    try:
        body = await request.json()
    except Exception:
        pass
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
    routes: list[RouteDefinition] = Field(min_length=1)

    def application(self) -> ApplicationDefinition:
        return ApplicationDefinition.model_validate(self.model_dump(exclude={"openapi_url"}))


class RouteSyncRequest(BaseModel):
    routes: list[RouteDefinition] = Field(min_length=1)


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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "master-chatbot"}


@app.post("/api/v1/registry/applications/register")
async def register_application(
    payload: ApplicationRegistrationRequest,
    _: None = Depends(_require_registration_key),
) -> dict[str, object]:
    application = application_registry.upsert(payload.application())
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
    configured = os.getenv(application.service_key_env, "")
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
    application = application_registry.get(payload.app_id)
    _require_app_service(application, service_key)
    if not application.base_url:
        raise HTTPException(status_code=503, detail="Application integration is not configured")
    if not application.chatbot.enabled:
        raise HTTPException(status_code=403, detail="Chatbot is disabled for this application")
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
        result = await workflow.run({"application": application, "message": safe_text(payload.message), "authorization": authorization if auth_state.authenticated else None, "auth_state": auth_state, "request_id": request_id, "history": conversation.turns})
        result["metadata"]["app_config"] = application.public_config()
        response = ChatResponse(app_id=payload.app_id, message=result["response_message"], data=result.get("data", []), intent=result["metadata"].get("route"), conversation_id=conversation_id, session_id=session_id, request_id=request_id, metadata=result["metadata"])
        # Keep recent API identifiers for follow-up actions; bound retained payload sizes.
        import json
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
