"""
Database engine, session factory, and base declarative class.

The DATABASE_URL environment variable selects the backend:
  sqlite+aiosqlite:///ai_configs.db  (default for local development)
  postgresql+psycopg://dev_chatbot:dev_chatbot@localhost:5432/chatbot_ai

If DATABASE_URL is not set, falls back to the local SQLite database
(ai_configs.db). Set DATABASE_URL for PostgreSQL or production environments.
"""
from __future__ import annotations

import os

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# ── Load .env if present ───────────────────────────────────────────────────
_SERVICE_ROOT = Path(__file__).resolve().parents[2]
for _env_candidate in (Path(__file__).resolve().parents[1] / ".env", _SERVICE_ROOT / ".env"):
    if _env_candidate.is_file():
        for line in _env_candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

# ── Resolve DATABASE_URL ────────────────────────────────────────────────────
_DEFAULT_SQLITE = f"sqlite+aiosqlite:///{Path(__file__).resolve().parents[1] / 'ai_configs.db'}"

DATABASE_URL: str = os.getenv("DATABASE_URL", _DEFAULT_SQLITE)

# If relative sqlite path, resolve it relative to service root
if DATABASE_URL.startswith("sqlite+aiosqlite:///") and not DATABASE_URL.startswith("sqlite+aiosqlite:////"):
    rel_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "")
    resolved_path = (_SERVICE_ROOT / rel_path).resolve()
    DATABASE_URL = f"sqlite+aiosqlite:///{resolved_path}"

# SQLite pragmas for dev
_connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
    connect_args=_connect_args,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[return]
    """FastAPI dependency that yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Create all tables that don't exist yet (dev / initial setup only).
    Production deployments should use Alembic migrations.
    """
    import uuid
    from datetime import datetime, timezone
    from sqlalchemy import select, func
    from sqlalchemy.exc import OperationalError
    from .db_models import AIProvider
    
    async with engine.begin() as conn:
        try:
            await conn.run_sync(Base.metadata.create_all)
        except OperationalError as e:
            # Ignore "already exists" errors for indexes/tables
            if "already exists" in str(e):
                pass
            else:
                raise
    
    # Seed initial AI providers if not already present
    async with AsyncSessionLocal() as session:
        try:
            # Check if providers already exist
            result = await session.execute(select(func.count(AIProvider.id)))
            count = result.scalar() or 0
            
            if count == 0:
                providers_data = [
                    {"name": "Groq", "provider_key": "groq", "description": "Fast inference, cost effective"},
                    {"name": "OpenAI", "provider_key": "openai", "description": "Advanced reasoning and tool use"},
                    {"name": "Google Gemini", "provider_key": "gemini", "description": "Google multimodal models"},
                    {"name": "Hugging Face", "provider_key": "huggingface", "description": "Open model hosting and inference"},
                ]
                
                for data in providers_data:
                    provider = AIProvider(
                        id=str(uuid.uuid4()),
                        name=data['name'],
                        provider_key=data['provider_key'],
                        description=data['description'],
                        is_enabled=True,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    session.add(provider)
                
                await session.commit()
        except Exception as e:
            # Table might not exist yet on first run, or providers already seeded
            import logging
            logging.getLogger(__name__).debug(f"Seed providers skipped: {e}")
