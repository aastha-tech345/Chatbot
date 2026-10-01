"""
SQLAlchemy ORM table definitions.

Naming conventions:
  - Separate from app/models.py (which contains Pydantic runtime models).
  - All UUIDs stored as TEXT for SQLite compatibility; cast on PG.
  - Timestamps stored as UTC datetime (timezone-aware on PG).
  - JSON columns use JSON type (maps to JSONB on PG via dialect inspection).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, Numeric,
    String, Text, UniqueConstraint, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
#  Admin users
# ─────────────────────────────────────────────────────────────────────────────

class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str]          = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str]  = mapped_column(Text, nullable=False)
    full_name: Mapped[str]      = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str]           = mapped_column(String(50), nullable=False, default="admin")
    is_active: Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    sessions: Mapped[list["AdminSession"]] = relationship("AdminSession", back_populates="admin_user", cascade="all, delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="admin_user")


# ─────────────────────────────────────────────────────────────────────────────
#  Admin sessions (JWT refresh tokens)
# ─────────────────────────────────────────────────────────────────────────────

class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    admin_user_id: Mapped[str]  = mapped_column(String(36), ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime]    = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip_address: Mapped[str | None]  = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None]  = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime]    = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime]    = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    admin_user: Mapped["AdminUser"] = relationship("AdminUser", back_populates="sessions")


# ─────────────────────────────────────────────────────────────────────────────
#  Applications (multi-app registry)
# ─────────────────────────────────────────────────────────────────────────────

class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str]           = mapped_column(String(255), nullable=False)
    app_id: Mapped[str]         = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_type: Mapped[str]   = mapped_column(String(50), nullable=False, default="web_application")
    category: Mapped[str | None]    = mapped_column(String(100), nullable=True)
    icon: Mapped[str | None]        = mapped_column(Text, nullable=True)
    base_url: Mapped[str]           = mapped_column(Text, nullable=False)
    api_docs_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str]             = mapped_column(String(20), nullable=False, default="active", index=True)

    openapi_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    discovery_mode: Mapped[str]     = mapped_column(String(20), nullable=False, default="dynamic")

    jwt_secret_env: Mapped[str | None]  = mapped_column(String(100), nullable=True)
    jwt_algorithm: Mapped[str]          = mapped_column(String(20), nullable=False, default="HS256")
    service_key_env: Mapped[str | None] = mapped_column(String(100), nullable=True)
    auth_type: Mapped[str | None]       = mapped_column(String(20), nullable=True)
    auth_config_json: Mapped[dict | None]   = mapped_column(JSON, nullable=True)
    chatbot_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_enabled: Mapped[bool]            = mapped_column(Boolean, nullable=False, default=True)
    last_discovered_at: Mapped[datetime | None]   = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    credentials: Mapped[list["ApplicationCredential"]] = relationship("ApplicationCredential", back_populates="application", cascade="all, delete-orphan")
    routes: Mapped[list["ApplicationRoute"]] = relationship("ApplicationRoute", back_populates="application", cascade="all, delete-orphan")
    settings: Mapped["ApplicationSettings | None"] = relationship("ApplicationSettings", back_populates="application", uselist=False, cascade="all, delete-orphan")
    request_logs: Mapped[list["ApiRequestLog"]] = relationship("ApiRequestLog", back_populates="application")


# ─────────────────────────────────────────────────────────────────────────────
#  Application credentials
# ─────────────────────────────────────────────────────────────────────────────

class ApplicationCredential(Base):
    __tablename__ = "application_credentials"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    auth_type: Mapped[str]      = mapped_column(String(20), nullable=False)

    api_key_encrypted: Mapped[str | None]           = mapped_column(Text, nullable=True)
    bearer_token_encrypted: Mapped[str | None]      = mapped_column(Text, nullable=True)
    client_id_encrypted: Mapped[str | None]         = mapped_column(Text, nullable=True)
    client_secret_encrypted: Mapped[str | None]     = mapped_column(Text, nullable=True)
    access_token_encrypted: Mapped[str | None]      = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None]     = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None]        = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    application: Mapped["Application"] = relationship("Application", back_populates="credentials")


# ─────────────────────────────────────────────────────────────────────────────
#  Application routes (OpenAPI discovery cache)
# ─────────────────────────────────────────────────────────────────────────────

class ApplicationRoute(Base):
    __tablename__ = "application_routes"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    method: Mapped[str]         = mapped_column(String(10), nullable=False, index=True)
    path: Mapped[str]           = mapped_column(Text, nullable=False, index=True)
    full_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation_id: Mapped[str | None]  = mapped_column(String(200), nullable=True)
    name: Mapped[str | None]          = mapped_column(String(200), nullable=True)
    summary: Mapped[str | None]       = mapped_column(Text, nullable=True)
    description: Mapped[str | None]   = mapped_column(Text, nullable=True)
    source: Mapped[str]               = mapped_column(String(20), nullable=False, default="openapi")
    auth_required: Mapped[bool]       = mapped_column(Boolean, nullable=False, default=False)
    auth_type: Mapped[str | None]     = mapped_column(String(20), nullable=True)
    status: Mapped[str]               = mapped_column(String(20), nullable=False, default="available")
    is_enabled: Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    request_schema_json: Mapped[dict | None]  = mapped_column(JSON, nullable=True)
    response_schema_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parameters_json: Mapped[dict | None]      = mapped_column(JSON, nullable=True)
    headers_json: Mapped[dict | None]         = mapped_column(JSON, nullable=True)
    query_params_json: Mapped[dict | None]    = mapped_column(JSON, nullable=True)
    path_params_json: Mapped[dict | None]     = mapped_column(JSON, nullable=True)
    request_body_json: Mapped[dict | None]    = mapped_column(JSON, nullable=True)
    content_type: Mapped[str | None]          = mapped_column(String(100), nullable=True)
    source_spec_version: Mapped[str | None]   = mapped_column(String(20), nullable=True)
    last_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    application: Mapped["Application"] = relationship("Application", back_populates="routes")

    __table_args__ = (
        UniqueConstraint("application_id", "method", "path", name="uq_app_route_method_path"),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  AI Providers
# ─────────────────────────────────────────────────────────────────────────────

class AIProvider(Base):
    __tablename__ = "ai_providers"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str]           = mapped_column(String(100), unique=True, nullable=False)
    provider_key: Mapped[str]   = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None]    = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool]    = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    credentials: Mapped[list["AICredential"]] = relationship("AICredential", back_populates="provider", cascade="all, delete-orphan")


# ─────────────────────────────────────────────────────────────────────────────
#  AI Credentials
# ─────────────────────────────────────────────────────────────────────────────

class AICredential(Base):
    __tablename__ = "ai_credentials"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    provider_id: Mapped[str]    = mapped_column(String(36), ForeignKey("ai_providers.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str]           = mapped_column(String(100), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str]          = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool]     = mapped_column(Boolean, nullable=False, default=False)
    temperature: Mapped[float | None]   = mapped_column(Numeric(4, 2), nullable=True)
    max_tokens: Mapped[int | None]      = mapped_column(Integer, nullable=True)
    top_p: Mapped[float | None]         = mapped_column(Numeric(4, 2), nullable=True)
    created_at: Mapped[datetime]        = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime]        = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    last_tested_at: Mapped[datetime | None]  = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[str | None]     = mapped_column(String(20), nullable=True)

    provider: Mapped["AIProvider"] = relationship("AIProvider", back_populates="credentials")


# ─────────────────────────────────────────────────────────────────────────────
#  Conversations
# ─────────────────────────────────────────────────────────────────────────────

class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    admin_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str | None]   = mapped_column(String(500), nullable=True)
    status: Mapped[str]         = mapped_column(String(20), nullable=False, default="active")
    context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None]        = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    messages: Mapped[list["Message"]] = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    request_logs: Mapped[list["ApiRequestLog"]] = relationship("ApiRequestLog", back_populates="conversation")


# ─────────────────────────────────────────────────────────────────────────────
#  Messages
# ─────────────────────────────────────────────────────────────────────────────

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str]           = mapped_column(String(20), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    message_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_name: Mapped[str | None]       = mapped_column(String(200), nullable=True)
    tool_call_id: Mapped[str | None]    = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime]        = mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
    request_logs: Mapped[list["ApiRequestLog"]] = relationship("ApiRequestLog", back_populates="message_record")


# ─────────────────────────────────────────────────────────────────────────────
#  API Request Logs
# ─────────────────────────────────────────────────────────────────────────────

class ApiRequestLog(Base):
    __tablename__ = "api_request_logs"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    message_id: Mapped[str | None]      = mapped_column(String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    admin_user_id: Mapped[str | None]   = mapped_column(String(36), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    method: Mapped[str | None]          = mapped_column(String(10), nullable=True)
    endpoint: Mapped[str | None]        = mapped_column(Text, nullable=True)
    source: Mapped[str | None]          = mapped_column(String(100), nullable=True)
    request_id: Mapped[str | None]      = mapped_column(String(200), nullable=True, index=True)
    status_code: Mapped[int | None]     = mapped_column(Integer, nullable=True)
    status: Mapped[str | None]          = mapped_column(String(50), nullable=True)
    level: Mapped[str]                  = mapped_column(String(20), nullable=False, index=True)
    message: Mapped[str | None]         = mapped_column(Text, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    error_code: Mapped[str | None]      = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None]   = mapped_column(Text, nullable=True)
    request_meta_json: Mapped[dict | None]  = mapped_column(JSON, nullable=True)
    response_meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime]        = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    application: Mapped["Application | None"] = relationship("Application", back_populates="request_logs")
    conversation: Mapped["Conversation | None"] = relationship("Conversation", back_populates="request_logs")
    message_record: Mapped["Message | None"] = relationship("Message", back_populates="request_logs")


# ─────────────────────────────────────────────────────────────────────────────
#  Audit Logs
# ─────────────────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    admin_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str]         = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None]   = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None]  = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None]  = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    admin_user: Mapped["AdminUser | None"] = relationship("AdminUser", back_populates="audit_logs")


# ─────────────────────────────────────────────────────────────────────────────
#  Application Settings
# ─────────────────────────────────────────────────────────────────────────────

class ApplicationSettings(Base):
    __tablename__ = "application_settings"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id", ondelete="CASCADE"), unique=True, nullable=False)
    timeout_seconds: Mapped[int]         = mapped_column(Integer, nullable=False, default=30)
    max_retries: Mapped[int]             = mapped_column(Integer, nullable=False, default=3)
    caching_enabled: Mapped[bool]        = mapped_column(Boolean, nullable=False, default=True)
    rate_limit_per_minute: Mapped[int | None]  = mapped_column(Integer, nullable=True)
    rate_limit_per_hour: Mapped[int | None]    = mapped_column(Integer, nullable=True)
    default_headers_json: Mapped[dict | None]  = mapped_column(JSON, nullable=True)
    webhook_config_json: Mapped[dict | None]   = mapped_column(JSON, nullable=True)
    advanced_config_json: Mapped[dict | None]  = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    application: Mapped["Application"] = relationship("Application", back_populates="settings")


# ─────────────────────────────────────────────────────────────────────────────
#  Global Settings
# ─────────────────────────────────────────────────────────────────────────────

class GlobalSetting(Base):
    __tablename__ = "global_settings"

    id: Mapped[str]             = mapped_column(String(36), primary_key=True, default=_uuid)
    setting_key: Mapped[str]    = mapped_column(String(100), unique=True, nullable=False, index=True)
    setting_value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
