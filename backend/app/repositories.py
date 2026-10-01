"""
Repository layer — all database queries live here.
Services call repositories; routes call services.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Sequence, Optional

from sqlalchemy import select, update, delete, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .db_models import (
    AdminUser, AdminSession, Application, ApplicationCredential,
    ApplicationRoute, ApplicationSettings, AIProvider, AICredential,
    Conversation, Message, ApiRequestLog, AuditLog, GlobalSetting,
)


# ─── Admin Users ────────────────────────────────────────────────────────────

class AdminUserRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_email(self, email: str) -> AdminUser | None:
        r = await self.db.execute(select(AdminUser).where(AdminUser.email == email.lower().strip()))
        return r.scalar_one_or_none()

    async def get_by_id(self, uid: str) -> AdminUser | None:
        r = await self.db.execute(select(AdminUser).where(AdminUser.id == uid))
        return r.scalar_one_or_none()

    async def create(self, *, email: str, password_hash: str, full_name: str, role: str = "admin") -> AdminUser:
        user = AdminUser(email=email.lower().strip(), password_hash=password_hash, full_name=full_name, role=role)
        self.db.add(user)
        await self.db.flush()
        return user

    async def update_last_login(self, uid: str) -> None:
        await self.db.execute(
            update(AdminUser).where(AdminUser.id == uid).values(last_login_at=datetime.now(timezone.utc))
        )

    async def update_password_hash(self, uid: str, password_hash: str) -> None:
        await self.db.execute(
            update(AdminUser)
            .where(AdminUser.id == uid)
            .values(password_hash=password_hash, updated_at=datetime.now(timezone.utc))
        )

    async def exists(self) -> bool:
        r = await self.db.execute(select(func.count()).select_from(AdminUser))
        return (r.scalar() or 0) > 0


# ─── Admin Sessions ──────────────────────────────────────────────────────────

class AdminSessionRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, admin_user_id: str, refresh_token_hash: str,
                     expires_at: datetime, ip_address: str | None = None,
                     user_agent: str | None = None) -> AdminSession:
        s = AdminSession(
            admin_user_id=admin_user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(s)
        await self.db.flush()
        return s

    async def get_active(self, token_hash: str) -> AdminSession | None:
        now = datetime.now(timezone.utc)
        r = await self.db.execute(
            select(AdminSession).where(
                and_(
                    AdminSession.refresh_token_hash == token_hash,
                    AdminSession.expires_at > now,
                    AdminSession.revoked_at.is_(None),
                )
            )
        )
        return r.scalar_one_or_none()

    async def revoke(self, session_id: str) -> None:
        await self.db.execute(
            update(AdminSession).where(AdminSession.id == session_id)
            .values(revoked_at=datetime.now(timezone.utc))
        )

    async def revoke_all_for_user(self, admin_user_id: str) -> None:
        await self.db.execute(
            update(AdminSession)
            .where(and_(AdminSession.admin_user_id == admin_user_id, AdminSession.revoked_at.is_(None)))
            .values(revoked_at=datetime.now(timezone.utc))
        )


# ─── Applications ────────────────────────────────────────────────────────────

class ApplicationRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> Sequence[Application]:
        r = await self.db.execute(select(Application).order_by(Application.name))
        return r.scalars().all()

    async def list_enabled(self) -> Sequence[Application]:
        """Return all enabled applications for runtime registry loading."""
        r = await self.db.execute(
            select(Application)
            .where(Application.is_enabled == True)
            .order_by(Application.name)
        )
        return r.scalars().all()

    async def get_by_id(self, uid: str) -> Application | None:
        r = await self.db.execute(select(Application).where(Application.id == uid))
        return r.scalar_one_or_none()

    async def get_by_app_id(self, app_id: str) -> Application | None:
        r = await self.db.execute(select(Application).where(Application.app_id == app_id))
        return r.scalar_one_or_none()

    async def create(self, data: dict) -> Application:
        app = Application(**data)
        self.db.add(app)
        await self.db.flush()
        return app

    async def update(self, uid: str, data: dict) -> Application | None:
        data["updated_at"] = datetime.now(timezone.utc)
        await self.db.execute(update(Application).where(Application.id == uid).values(**data))
        return await self.get_by_id(uid)

    async def delete(self, uid: str) -> bool:
        app = await self.get_by_id(uid)
        if app is None:
            return False
        # Honor the existing ORM delete-orphan relationships on SQLite as well.
        await self.db.delete(app)
        await self.db.flush()
        return True

    async def update_discovery_timestamp(self, uid: str) -> None:
        await self.db.execute(
            update(Application).where(Application.id == uid)
            .values(last_discovered_at=datetime.now(timezone.utc))
        )

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
        """Return paginated, filtered, and sorted applications with total count."""
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        
        # Build filters
        conditions = []
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append(
                (Application.name.ilike(pattern)) |
                (Application.app_id.ilike(pattern)) |
                (Application.description.ilike(pattern)) |
                (Application.base_url.ilike(pattern))
            )
        if status:
            conditions.append(Application.status == status)
        if application_type:
            conditions.append(Application.application_type == application_type)
        if category:
            conditions.append(Application.category == category)
        if is_enabled is not None:
            conditions.append(Application.is_enabled == is_enabled)
        
        # Build query
        q = select(Application)
        if conditions:
            q = q.where(*conditions)
        
        # Count total before pagination
        count_r = await self.db.execute(select(func.count()).select_from(Application).where(*conditions) if conditions else select(func.count()).select_from(Application))
        total = int(count_r.scalar() or 0)
        
        # Sort
        sort_col = getattr(Application, sort_by, Application.created_at)
        if sort_order.lower() == "asc":
            q = q.order_by(sort_col.asc())
        else:
            q = q.order_by(sort_col.desc())
        
        # Paginate
        q = q.offset((page - 1) * page_size).limit(page_size)
        
        r = await self.db.execute(q)
        items = r.scalars().all()
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }


# ─── Application Routes ───────────────────────────────────────────────────────

class ApplicationRouteRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_app(
        self,
        application_id: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
        search: str | None = None,
        method: str | None = None,
        status: str | None = None,
    ) -> Sequence[ApplicationRoute]:
        query = (
            select(ApplicationRoute)
            .where(ApplicationRoute.application_id == application_id)
            .order_by(ApplicationRoute.path, ApplicationRoute.method)
        )
        conditions = self._route_filters(search=search, method=method, status=status)
        if conditions:
            query = query.where(*conditions)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        r = await self.db.execute(query)
        return r.scalars().all()

    async def count_for_app(
        self,
        application_id: str,
        *,
        search: str | None = None,
        method: str | None = None,
        status: str | None = None,
    ) -> int:
        conditions = self._route_filters(search=search, method=method, status=status)
        r = await self.db.execute(
            select(func.count()).select_from(ApplicationRoute)
            .where(ApplicationRoute.application_id == application_id)
            .where(*conditions)
        )
        return int(r.scalar() or 0)

    def _route_filters(self, *, search: str | None, method: str | None, status: str | None) -> list:
        conditions = []
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append(
                ApplicationRoute.path.ilike(pattern) |
                ApplicationRoute.description.ilike(pattern) |
                ApplicationRoute.summary.ilike(pattern) |
                ApplicationRoute.operation_id.ilike(pattern)
            )
        if method:
            conditions.append(ApplicationRoute.method == method.upper())
        if status:
            normalized = status.lower()
            if normalized == "available":
                conditions.append(ApplicationRoute.is_enabled.is_(True))
            elif normalized == "disabled":
                conditions.append(ApplicationRoute.is_enabled.is_(False))
            else:
                conditions.append(ApplicationRoute.status == normalized)
        return conditions

    async def get_by_id(self, route_id: str) -> ApplicationRoute | None:
        r = await self.db.execute(select(ApplicationRoute).where(ApplicationRoute.id == route_id))
        return r.scalar_one_or_none()

    async def upsert_routes(self, application_id: str, routes: list[dict], *, source: str | None = None) -> None:
        """Replace routes for an application atomically.

        When source is provided, only routes from that source are replaced. This
        lets OpenAPI rediscovery refresh discovered routes while preserving
        manually registered routes.
        """
        conditions = [ApplicationRoute.application_id == application_id]
        if source:
            conditions.append(ApplicationRoute.source == source)
        await self.db.execute(delete(ApplicationRoute).where(*conditions))
        for r in routes:
            self.db.add(ApplicationRoute(application_id=application_id, **r))
        await self.db.flush()

    async def create(self, application_id: str, data: dict) -> ApplicationRoute:
        route = ApplicationRoute(application_id=application_id, **data)
        self.db.add(route)
        await self.db.flush()
        return route

    async def update(self, route_id: str, data: dict) -> ApplicationRoute | None:
        data["updated_at"] = datetime.now(timezone.utc)
        await self.db.execute(update(ApplicationRoute).where(ApplicationRoute.id == route_id).values(**data))
        return await self.get_by_id(route_id)

    async def delete(self, route_id: str) -> bool:
        r = await self.db.execute(delete(ApplicationRoute).where(ApplicationRoute.id == route_id))
        return r.rowcount > 0

    async def update_status(self, route_id: str, status: str, is_enabled: bool) -> None:
        await self.db.execute(
            update(ApplicationRoute).where(ApplicationRoute.id == route_id)
            .values(status=status, is_enabled=is_enabled, updated_at=datetime.now(timezone.utc))
        )


# ─── Application Credentials (per-app JWT secret + service key) ──────────────

class ApplicationCredentialRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_app(self, application_id: str) -> Sequence[ApplicationCredential]:
        r = await self.db.execute(
            select(ApplicationCredential)
            .where(ApplicationCredential.application_id == application_id)
            .order_by(ApplicationCredential.created_at.desc())
        )
        return r.scalars().all()

    async def get_active_for_app(self, application_id: str, auth_type: str) -> ApplicationCredential | None:
        r = await self.db.execute(
            select(ApplicationCredential)
            .where(
                ApplicationCredential.application_id == application_id,
                ApplicationCredential.auth_type == auth_type,
                ApplicationCredential.is_active == True,
            )
        )
        return r.scalar_one_or_none()

    async def upsert(self, application_id: str, auth_type: str, data: dict) -> ApplicationCredential:
        # Serialize credential writes, including the first insert.
        await self.db.execute(select(Application.id).where(Application.id == application_id).with_for_update())
        existing = await self.get_active_for_app(application_id, auth_type)
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            return existing
        cred = ApplicationCredential(application_id=application_id, auth_type=auth_type, **data)
        self.db.add(cred)
        await self.db.flush()
        return cred


# ─── AI Providers ────────────────────────────────────────────────────────────

class AIProviderRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self, enabled_only: bool = False) -> Sequence[AIProvider]:
        q = select(AIProvider).order_by(AIProvider.name)
        if enabled_only:
            q = q.where(AIProvider.is_enabled == True)
        r = await self.db.execute(q)
        return r.scalars().all()

    async def get_by_key(self, key: str) -> AIProvider | None:
        r = await self.db.execute(select(AIProvider).where(AIProvider.provider_key == key))
        return r.scalar_one_or_none()

    async def get_by_id(self, uid: str) -> AIProvider | None:
        r = await self.db.execute(select(AIProvider).where(AIProvider.id == uid))
        return r.scalar_one_or_none()

    async def create(self, data: dict) -> AIProvider:
        provider = AIProvider(**data)
        self.db.add(provider)
        await self.db.flush()
        return provider

    async def update(self, uid: str, data: dict) -> AIProvider | None:
        data["updated_at"] = datetime.now(timezone.utc)
        await self.db.execute(update(AIProvider).where(AIProvider.id == uid).values(**data))
        return await self.get_by_id(uid)

    async def delete(self, uid: str) -> bool:
        r = await self.db.execute(delete(AIProvider).where(AIProvider.id == uid))
        return r.rowcount > 0

    async def count_credentials(self, provider_id: str) -> int:
        r = await self.db.execute(
            select(func.count()).select_from(AICredential)
            .where(AICredential.provider_id == provider_id)
        )
        return int(r.scalar() or 0)


# ─── AI Credentials ───────────────────────────────────────────────────────────

class AICredentialRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all(self) -> Sequence[AICredential]:
        r = await self.db.execute(select(AICredential).order_by(AICredential.created_at.desc()))
        return r.scalars().all()

    async def get_by_id(self, uid: str) -> AICredential | None:
        r = await self.db.execute(select(AICredential).where(AICredential.id == uid))
        return r.scalar_one_or_none()

    async def get_active(self) -> AICredential | None:
        r = await self.db.execute(select(AICredential).where(AICredential.is_active == True))
        return r.scalar_one_or_none()

    async def create(self, data: dict) -> AICredential:
        cred = AICredential(**data)
        self.db.add(cred)
        await self.db.flush()
        return cred

    async def update(self, uid: str, data: dict) -> AICredential | None:
        data["updated_at"] = datetime.now(timezone.utc)
        await self.db.execute(update(AICredential).where(AICredential.id == uid).values(**data))
        return await self.get_by_id(uid)

    async def delete(self, uid: str) -> bool:
        r = await self.db.execute(delete(AICredential).where(AICredential.id == uid))
        return r.rowcount > 0

    async def deactivate_for_provider(self, provider_id: str) -> None:
        """Deactivate all credentials for one provider before activating one."""
        await self.db.execute(
            update(AICredential)
            .where(AICredential.provider_id == provider_id)
            .values(is_active=False)
        )

    async def deactivate(self, uid: str) -> AICredential | None:
        """Deactivate a single credential by ID."""
        await self.db.execute(
            update(AICredential).where(AICredential.id == uid)
            .values(is_active=False, updated_at=datetime.now(timezone.utc))
        )
        return await self.get_by_id(uid)

    async def activate(self, uid: str) -> AICredential | None:
        cred = await self.get_by_id(uid)
        if not cred:
            return None
        await self.deactivate_for_provider(cred.provider_id)
        await self.db.execute(
            update(AICredential).where(AICredential.id == uid)
            .values(is_active=True, updated_at=datetime.now(timezone.utc))
        )
        return await self.get_by_id(uid)

    async def record_test(self, uid: str, status: str) -> None:
        await self.db.execute(
            update(AICredential).where(AICredential.id == uid)
            .values(last_tested_at=datetime.now(timezone.utc), last_test_status=status)
        )


# ─── Conversations ────────────────────────────────────────────────────────────

class ConversationRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> Conversation:
        c = Conversation(**data)
        self.db.add(c)
        await self.db.flush()
        return c

    async def get_by_id(self, uid: str) -> Conversation | None:
        r = await self.db.execute(select(Conversation).where(Conversation.id == uid))
        return r.scalar_one_or_none()

    async def list_recent(self, limit: int = 50) -> Sequence[Conversation]:
        r = await self.db.execute(
            select(Conversation).order_by(Conversation.last_message_at.desc().nullslast()).limit(limit)
        )
        return r.scalars().all()

    async def add_message(self, data: dict) -> Message:
        m = Message(**data)
        self.db.add(m)
        await self.db.execute(
            update(Conversation).where(Conversation.id == data["conversation_id"])
            .values(last_message_at=datetime.now(timezone.utc))
        )
        await self.db.flush()
        return m

    async def get_messages(self, conversation_id: str) -> Sequence[Message]:
        r = await self.db.execute(
            select(Message).where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return r.scalars().all()


# ─── API Request Logs ─────────────────────────────────────────────────────────

class ApiRequestLogRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> ApiRequestLog:
        # Strip any accidentally included auth/secret fields
        _FORBIDDEN = {"authorization", "api_key", "token", "password", "secret", "bearer"}
        safe = {k: v for k, v in data.items() if k.lower() not in _FORBIDDEN}
        log = ApiRequestLog(**safe)
        self.db.add(log)
        await self.db.flush()
        return log

    async def list_recent(self, *, limit: int = 200, application_id: str | None = None,
                          level: str | None = None) -> Sequence[ApiRequestLog]:
        q = select(ApiRequestLog)
        if application_id:
            q = q.where(ApiRequestLog.application_id == application_id)
        if level:
            q = q.where(ApiRequestLog.level == level.upper())
        q = q.order_by(ApiRequestLog.created_at.desc()).limit(limit)
        r = await self.db.execute(q)
        return r.scalars().all()

    async def list_paginated(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        application_id: str | None = None,
        level: str | None = None,
        status: str | None = None,
        method: str | None = None,
        source: str | None = None,
    ) -> dict:
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        conditions = []
        if application_id:
            conditions.append(ApiRequestLog.application_id == application_id)
        if level:
            conditions.append(ApiRequestLog.level == level.upper())
        if status:
            conditions.append(ApiRequestLog.status == status.upper())
        if method:
            conditions.append(ApiRequestLog.method == method.upper())
        if source:
            conditions.append(ApiRequestLog.source == source)
        if search:
            pattern = f"%{search.strip()}%"
            conditions.append(or_(
                ApiRequestLog.message.ilike(pattern),
                ApiRequestLog.endpoint.ilike(pattern),
                ApiRequestLog.request_id.ilike(pattern),
                ApiRequestLog.error_message.ilike(pattern),
            ))
        count_q = select(func.count()).select_from(ApiRequestLog)
        q = select(ApiRequestLog)
        if conditions:
            count_q = count_q.where(*conditions)
            q = q.where(*conditions)
        total_r = await self.db.execute(count_q)
        total = int(total_r.scalar() or 0)
        q = q.order_by(ApiRequestLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(q)).scalars().all()
        return {
            "items": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }


# ─── Audit Logs ───────────────────────────────────────────────────────────────

class AuditLogRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def record(self, *, action: str, admin_user_id: str | None = None,
                     entity_type: str | None = None, entity_id: str | None = None,
                     description: str | None = None, ip_address: str | None = None,
                     user_agent: str | None = None, metadata: dict | None = None) -> AuditLog:
        entry = AuditLog(
            admin_user_id=admin_user_id, action=action,
            entity_type=entity_type, entity_id=entity_id,
            description=description, ip_address=ip_address,
            user_agent=user_agent, metadata_json=metadata,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry


# ─── Global Settings ─────────────────────────────────────────────────────────

class GlobalSettingRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, key: str) -> GlobalSetting | None:
        r = await self.db.execute(select(GlobalSetting).where(GlobalSetting.setting_key == key))
        return r.scalar_one_or_none()

    async def get_all(self) -> Sequence[GlobalSetting]:
        r = await self.db.execute(select(GlobalSetting).order_by(GlobalSetting.setting_key))
        return r.scalars().all()

    async def upsert(self, key: str, value: object, updated_by: str | None = None) -> GlobalSetting:
        existing = await self.get(key)
        if existing:
            existing.setting_value_json = value  # type: ignore[assignment]
            existing.updated_by = updated_by
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            return existing
        s = GlobalSetting(setting_key=key, setting_value_json=value, updated_by=updated_by)
        self.db.add(s)
        await self.db.flush()
        return s
