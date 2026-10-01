from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class HTTPMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class RouteDefinition(BaseModel):
    """An application-owned HTTP contract exposed to the orchestration engine."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    method: HTTPMethod
    path: str = Field(pattern=r"^/")
    description: str = Field(min_length=1)
    parameters: dict[str, str] = Field(default_factory=dict)
    required_parameters: list[str] = Field(default_factory=list)
    app_id: str | None = None
    visibility: Literal["public", "private"] = "private"
    requires_auth: bool = True
    requires_user_context: bool = False
    allowed_roles: list[str] = Field(default_factory=list)
    supported_operations: list[str] = Field(default_factory=list)
    authentication_strategy: str | None = None

    @property
    def protected(self) -> bool:
        # Fail closed if ANY metadata requires authentication.
        return self.visibility != "public" or self.requires_auth or self.requires_user_context or bool(self.allowed_roles)


class AuthenticationField(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    label: str = Field(min_length=1, max_length=100)
    type: Literal["text", "email", "password", "tel", "date", "otp"] = "text"
    required: bool = True
    sensitive: bool = False


class AuthenticationConfig(BaseModel):
    enabled: bool = False
    login_required_for_private_data: bool = True
    method: str = "external"
    fields: list[AuthenticationField] = Field(default_factory=list, max_length=12)
    action_label: str = "Sign in"
    verification: Literal["jwt", "introspection"] = "jwt"
    user_info_path: str | None = None
    principal_field: str = "id"
    roles_field: str = "roles"
    audience: str | None = None
    issuer: str | None = None

    @model_validator(mode="after")
    def validate_config(self):
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("Authentication field names must be unique")
        if self.user_info_path and (not self.user_info_path.startswith("/") or self.user_info_path.startswith("//") or ".." in self.user_info_path):
            raise ValueError("User info path must be an application-local path")
        return self

    def public_config(self) -> dict[str, Any]:
        return self.model_dump(include={"enabled", "login_required_for_private_data", "method", "fields", "action_label"})


class LinkedApplication(BaseModel):
    app_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str


class ChatbotConfig(BaseModel):
    enabled: bool = True
    welcome_message: str = "Hi! How can I help you today?"
    quick_actions: list[str] = Field(default_factory=list, max_length=12)


class ApplicationDefinition(BaseModel):
    app_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    # A deployment can register an application before its environment values are set.
    # Requests reject an incomplete integration; startup and health checks remain available.
    base_url: str = ""
    jwt_secret_env: str = ""
    jwt_algorithm: str = "HS256"
    service_key_env: str = Field(min_length=1)
    routes: list[RouteDefinition] = Field(min_length=1)
    authentication: AuthenticationConfig = Field(default_factory=AuthenticationConfig)
    chatbot: ChatbotConfig = Field(default_factory=ChatbotConfig)
    linked_applications: list[LinkedApplication] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_route_apps(self):
        for route in self.routes:
            if route.app_id is not None and route.app_id != self.app_id:
                raise ValueError("Route app_id must match its owning application")
        return self

    def public_config(self) -> dict[str, Any]:
        return {"app_id": self.app_id, "app_name": self.name, "authentication": self.authentication.public_config(), "chatbot": self.chatbot.model_dump(), "linked_applications": [app.model_dump() for app in self.linked_applications]}


class ReadQuery(BaseModel):
    route_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class RoutePlan(BaseModel):
    route_name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    clarification: str | None = None
    target_app_id: str | None = None

    comparison_reads: list[ReadQuery] = Field(default_factory=list, max_length=3)
