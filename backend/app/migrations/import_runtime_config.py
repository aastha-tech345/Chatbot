"""
One-time migration: .env + applications.json → Database

Usage:
    cd Master-Chatbot/chatbot/backend
    python -m app.migrations.import_runtime_config

This script is IDEMPOTENT — safe to run multiple times.
It will skip records that already exist (based on app_id / provider_key).
It will NEVER delete .env or applications.json.
It will NEVER print secrets.

Classification of .env variables:
  A. Infrastructure/Bootstrap: DATABASE_URL, SECRET_KEY, JWT_SECRET_KEY,
     CORS_ORIGINS, HOST, PORT, MASTER_CHATBOT_* keys
  B. Application runtime: {APP}_API_URL, {APP}_JWT_SECRET, {APP}_JWT_ALGORITHM,
     {APP}_MASTER_CHATBOT_SERVICE_KEY
  C. AI runtime: AI_PROVIDER, GROQ_API_KEY, GROQ_MODEL
  D. Legacy/unused: ACCESS_TOKEN_EXPIRE_SECONDS, REFRESH_TOKEN_EXPIRE_SECONDS
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Add the backend directory to sys.path so imports work
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SERVICE_ROOT = _BACKEND_DIR.parent  # chatbot/
sys.path.insert(0, str(_BACKEND_DIR))


def _load_env_file(env_path: Path) -> dict[str, str]:
    """Load .env file into a dict without overwriting os.environ."""
    result: dict[str, str] = {}
    if not env_path.is_file():
        return result
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


def _safe(value: str, show: int = 0) -> str:
    """Return masked string — never expose secrets in output."""
    if not value:
        return "(empty)"
    if show > 0:
        return f"{'*' * 8}{value[-show:]}" if len(value) > show else "****"
    return f"{'*' * 8}(configured)"


async def run_migration() -> None:
    from app.database import AsyncSessionLocal, create_tables
    from app.crypto import encrypt
    from app.repositories import (
        ApplicationRepo, ApplicationCredentialRepo,
        AIProviderRepo, AICredentialRepo,
    )
    from app.db_models import Application, ApplicationCredential, AIProvider, AICredential

    # ── Load source files ──────────────────────────────────────────────────
    env_path = _SERVICE_ROOT / ".env"
    env_vars = _load_env_file(env_path)

    # Also load from os.environ (already set from config.py bootstrap)
    for key in list(env_vars):
        if key not in os.environ:
            os.environ.setdefault(key, env_vars[key])

    print(f"[MIGRATION] .env path: {env_path} (exists={env_path.exists()})")

    applications_json_path = _SERVICE_ROOT / "config" / "applications.json"
    print(f"[MIGRATION] applications.json path: {applications_json_path} (exists={applications_json_path.exists()})")

    # ── Parse applications.json ────────────────────────────────────────────
    json_apps: list[dict] = []
    if applications_json_path.is_file():
        try:
            raw = json.loads(applications_json_path.read_text(encoding="utf-8"))
            json_apps = raw.get("applications", [])
            print(f"[MIGRATION] applications discovered in applications.json: {len(json_apps)}")
        except Exception as exc:
            print(f"[MIGRATION] WARNING: Could not parse applications.json: {exc}")

    # ── Detect application IDs from .env ───────────────────────────────────
    # Pattern: {PREFIX}_API_URL → app_id = prefix.lower()
    env_app_ids: set[str] = set()
    for key in env_vars:
        if key.endswith("_API_URL"):
            prefix = key[: -len("_API_URL")]
            if prefix and prefix.upper() == prefix and not prefix.startswith("MASTER_CHATBOT"):
                env_app_ids.add(prefix.lower())

    # Merge with applications.json app_ids
    all_app_ids = env_app_ids | {a.get("app_id", "") for a in json_apps if a.get("app_id")}
    print(f"[MIGRATION] application IDs to migrate: {sorted(all_app_ids)}")

    # ── Detect AI provider from .env ───────────────────────────────────────
    ai_provider_key = env_vars.get("AI_PROVIDER", os.getenv("AI_PROVIDER", "")).strip().lower()
    groq_api_key = env_vars.get("GROQ_API_KEY", os.getenv("GROQ_API_KEY", "")).strip()
    groq_model = env_vars.get("GROQ_MODEL", os.getenv("GROQ_MODEL", "")).strip()

    print(f"[MIGRATION] AI provider from .env: {ai_provider_key or '(not set)'}")
    print(f"[MIGRATION] AI model from .env: {groq_model or '(not set)'}")
    # Never print API key

    # ── Ensure tables exist ────────────────────────────────────────────────
    await create_tables()

    apps_migrated = 0
    creds_migrated = 0
    providers_migrated = 0
    ai_configs_migrated = 0

    async with AsyncSessionLocal() as db:
        app_repo = ApplicationRepo(db)
        cred_repo = ApplicationCredentialRepo(db)
        ai_provider_repo = AIProviderRepo(db)
        ai_cred_repo = AICredentialRepo(db)

        # ── 1. Migrate applications ────────────────────────────────────────
        for app_id in sorted(all_app_ids):
            if not app_id:
                continue

            prefix = app_id.upper()

            # Resolve values — prefer applications.json, supplement from .env
            json_app = next((a for a in json_apps if a.get("app_id") == app_id), {})

            api_url = (
                json_app.get("base_url")
                or env_vars.get(f"{prefix}_API_URL", os.getenv(f"{prefix}_API_URL", ""))
            ).rstrip("/")

            openapi_url = json_app.get("openapi_url") or ""
            discovery_mode = json_app.get("discovery_mode", "dynamic")
            jwt_algorithm = (
                json_app.get("jwt_algorithm")
                or env_vars.get(f"{prefix}_JWT_ALGORITHM", os.getenv(f"{prefix}_JWT_ALGORITHM", "HS256"))
            )
            app_name = json_app.get("name", app_id.title())

            jwt_secret = (
                env_vars.get(f"{prefix}_JWT_SECRET", os.getenv(f"{prefix}_JWT_SECRET", ""))
            )
            service_key = (
                env_vars.get(f"{prefix}_MASTER_CHATBOT_SERVICE_KEY",
                              os.getenv(f"{prefix}_MASTER_CHATBOT_SERVICE_KEY", ""))
            )

            auth_config_json = json_app.get("authentication") or None
            chatbot_config_json = json_app.get("chatbot") or None

            # Check if application already exists
            existing_app = await app_repo.get_by_app_id(app_id)
            if existing_app:
                print(f"[MIGRATION] application '{app_id}' already exists in DB — skipping (use update if needed)")
            else:
                app_data: dict = {
                    "app_id": app_id,
                    "name": app_name,
                    "base_url": api_url,
                    "openapi_url": openapi_url or None,
                    "discovery_mode": discovery_mode,
                    "jwt_algorithm": jwt_algorithm,
                    "auth_config_json": auth_config_json,
                    "chatbot_config_json": chatbot_config_json,
                    "is_enabled": True,
                    "status": "active",
                    "description": f"Migrated from .env / applications.json",
                }
                existing_app = await app_repo.create(app_data)
                apps_migrated += 1
                print(f"[MIGRATION] application '{app_id}' migrated (name='{app_name}' base_url={'(set)' if api_url else '(empty)'})")

            # Store JWT secret as ApplicationCredential (type=jwt)
            if jwt_secret:
                existing_jwt = await cred_repo.get_active_for_app(existing_app.id, "jwt")
                if existing_jwt:
                    print(f"[MIGRATION] jwt credential for '{app_id}' already exists — skipping")
                else:
                    await cred_repo.upsert(existing_app.id, "jwt", {
                        "api_key_encrypted": encrypt(jwt_secret),
                        "is_active": True,
                    })
                    creds_migrated += 1
                    print(f"[MIGRATION] jwt secret for '{app_id}' stored securely")
            else:
                print(f"[MIGRATION] no JWT secret found for '{app_id}' — skipping")

            # Store service key as ApplicationCredential (type=service_key)
            if service_key:
                existing_sk = await cred_repo.get_active_for_app(existing_app.id, "service_key")
                if existing_sk:
                    print(f"[MIGRATION] service_key credential for '{app_id}' already exists — skipping")
                else:
                    await cred_repo.upsert(existing_app.id, "service_key", {
                        "bearer_token_encrypted": encrypt(service_key),
                        "is_active": True,
                    })
                    creds_migrated += 1
                    print(f"[MIGRATION] service key for '{app_id}' stored securely")
            else:
                print(f"[MIGRATION] no service key found for '{app_id}' — skipping")

        # ── 2. Migrate AI provider ─────────────────────────────────────────
        if ai_provider_key:
            _PROVIDER_META = {
                "groq": {"name": "Groq", "description": "Groq LPU Inference Engine", "icon": "groq"},
                "openai": {"name": "OpenAI", "description": "OpenAI GPT models", "icon": "openai"},
                "gemini": {"name": "Google Gemini", "description": "Google Gemini models", "icon": "gemini"},
            }

            existing_provider = await ai_provider_repo.get_by_key(ai_provider_key)
            if existing_provider:
                print(f"[MIGRATION] AI provider '{ai_provider_key}' already exists in DB — skipping")
            else:
                meta = _PROVIDER_META.get(ai_provider_key, {})
                provider_data = {
                    "provider_key": ai_provider_key,
                    "name": meta.get("name", ai_provider_key.title()),
                    "description": meta.get("description", f"{ai_provider_key.title()} AI provider"),
                    "icon": meta.get("icon"),
                    "is_enabled": True,
                }
                existing_provider = await ai_provider_repo.create(provider_data)
                providers_migrated += 1
                print(f"[MIGRATION] AI provider '{ai_provider_key}' migrated")

            # ── 3. Migrate AI credential ───────────────────────────────────
            if groq_api_key:
                existing_cred = await ai_cred_repo.get_active()
                if existing_cred:
                    print(f"[MIGRATION] active AI credential already exists (name='{existing_cred.name}') — skipping")
                else:
                    ai_cred_data = {
                        "provider_id": existing_provider.id,
                        "name": f"{existing_provider.name} (migrated from .env)",
                        "api_key_encrypted": encrypt(groq_api_key),
                        "model": groq_model or "llama3-70b-8192",
                        "is_active": True,
                        "temperature": None,
                        "max_tokens": None,
                        "top_p": None,
                    }
                    await ai_cred_repo.create(ai_cred_data)
                    ai_configs_migrated += 1
                    print(f"[MIGRATION] AI credential for '{ai_provider_key}' stored securely (model={groq_model or 'llama3-70b-8192'})")
            else:
                print(f"[MIGRATION] no API key found for AI provider '{ai_provider_key}' — skipping credential migration")
        else:
            print("[MIGRATION] AI_PROVIDER not set in .env — skipping AI migration")

        await db.commit()

    # ── Summary ────────────────────────────────────────────────────────────
    print()
    print(f"[MIGRATION] applications discovered: {len(all_app_ids)}")
    print(f"[MIGRATION] applications migrated: {apps_migrated}")
    print(f"[MIGRATION] credentials migrated: {creds_migrated}")
    print(f"[MIGRATION] AI providers migrated: {providers_migrated}")
    print(f"[MIGRATION] AI configurations migrated: {ai_configs_migrated}")
    print("[MIGRATION] secrets stored securely")
    print("[MIGRATION] .env NOT modified or deleted")
    print("[MIGRATION] applications.json NOT modified or deleted")
    print("[MIGRATION] completed successfully")


if __name__ == "__main__":
    # Set up environment from .env before importing app modules
    env_path = _SERVICE_ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)

    asyncio.run(run_migration())
