"""Data models for Master Chatbot Client SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class UserContext:
    """Authenticated user context passed to Master Chatbot."""

    principal_id: str
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    session_id: Optional[str] = None
    request_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.principal_id.strip():
            raise ValueError("principal_id is required")


@dataclass
class ChatRequest:
    """Request to send to Master Chatbot (internal SDK model)."""

    app_id: str
    message: str
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.app_id.strip():
            raise ValueError("app_id is required")
        if not self.message.strip():
            raise ValueError("message is required")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {
            "app_id": self.app_id,
            "message": self.message,
        }
        if self.conversation_id is not None:
            data["conversation_id"] = self.conversation_id
        if self.session_id is not None:
            data["session_id"] = self.session_id
        if self.request_id is not None:
            data["request_id"] = self.request_id
        return data


@dataclass
class ChatResponse:
    """Response from Master Chatbot (SDK model)."""

    success: bool
    app_id: str
    conversation_id: str
    message: str
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    intent: Optional[str] = None
    data: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatResponse:
        """Create from API response dictionary."""
        required = ("app_id", "conversation_id", "message")
        missing = [field_name for field_name in required if not isinstance(data.get(field_name), str)]
        if missing:
            raise ValueError(f"Invalid chat response; missing: {', '.join(missing)}")
        return cls(
            success=data.get("success", True),
            app_id=data.get("app_id", ""),
            conversation_id=data.get("conversation_id", ""),
            session_id=data.get("session_id"),
            request_id=data.get("request_id"),
            message=data.get("message", ""),
            intent=data.get("intent"),
            data=data.get("data", []),
            actions=data.get("actions", []),
            metadata=data.get("metadata", {}),
        )
