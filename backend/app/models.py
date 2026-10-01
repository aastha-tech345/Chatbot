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


class RouteStatus(str, Enum):
    """Route availability status in the application registry."""
    AVAILABLE = "Available"
    DISABLED = "Disabled"
    ERROR = "Error"

    @classmethod
    def normalize(cls, value: str | None) -> str:
        """Normalize any status representation to canonical uppercase form.

        Accepts:
        - "Available", "available"
        - "Disabled", "disabled"
        - "Error", "error"
        - None (defaults to AVAILABLE)

        Returns the canonical enum value string.
        """
        if not value:
            return cls.AVAILABLE.value
        value_lower = str(value).strip().lower()
        if value_lower == "available":
            return cls.AVAILABLE.value
        elif value_lower == "disabled":
            return cls.DISABLED.value
        elif value_lower == "error":
            return cls.ERROR.value
        # Default to AVAILABLE for unknown values
        return cls.AVAILABLE.value


class RouteErrorCode(str, Enum):
    """Structured error codes for route execution failures."""
    ROUTE_AVAILABLE = "ROUTE_AVAILABLE"
    ROUTE_DISABLED = "ROUTE_DISABLED"
    ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
    ROUTE_DISCOVERY_FAILED = "ROUTE_DISCOVERY_FAILED"
    APPLICATION_DISABLED = "APPLICATION_DISABLED"
    APPLICATION_NOT_FOUND = "APPLICATION_NOT_FOUND"


def is_route_available(route: RouteDefinition) -> bool:
    """Check if a route is available for execution.
    
    A route is available if:
    - is_enabled is True AND
    - status is AVAILABLE
    """
    return route.is_enabled and route.status == RouteStatus.AVAILABLE.value


def is_route_disabled(route: RouteDefinition) -> bool:
    """Check if a route is disabled.
    
    A route is disabled if:
    - is_enabled is False OR
    - status is DISABLED or ERROR
    """
    return not route.is_enabled or route.status in {RouteStatus.DISABLED.value, RouteStatus.ERROR.value}


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
    source: Literal["openapi", "manual"] = "openapi"
    # Route availability tracking
    is_enabled: bool = True
    status: RouteStatus = RouteStatus.AVAILABLE

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
    # OpenAPI discovery support
    openapi_url: str | None = None
    discovery_mode: str = "manual"  # "dynamic_openapi", "manual", or "hybrid"
    routes: list[RouteDefinition] = Field(default_factory=list)
    authentication: AuthenticationConfig = Field(default_factory=AuthenticationConfig)
    chatbot: ChatbotConfig = Field(default_factory=ChatbotConfig)
    linked_applications: list[LinkedApplication] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_route_apps(self):
        aliases = {"dynamic": "dynamic_openapi", "static": "manual"}
        self.discovery_mode = aliases.get(self.discovery_mode, self.discovery_mode)
        # DB-first modes can register before routes have been discovered/manual-added.
        if self.discovery_mode in {"dynamic_openapi", "manual", "hybrid"}:
            if not self.routes:
                return self
        if self.discovery_mode not in {"dynamic_openapi", "manual", "hybrid"} and not self.routes:
            raise ValueError("Routes are required for static discovery mode")
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
