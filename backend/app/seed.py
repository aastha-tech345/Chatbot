"""
Development seed script.

Creates the first admin user and default global settings if they don't exist.
Run with:
    python -m app.seed

Admin credentials come from environment variables:
    ADMIN_EMAIL    (default: admin@master-chatbot.local)
    ADMIN_PASSWORD (default: changeme — CHANGE THIS in production)
    ADMIN_NAME     (default: Administrator)

NEVER hardcode passwords in source code.
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


async def seed() -> None:
    from .database import AsyncSessionLocal
    from .services import AuthService, SettingsService
    from .repositories import AdminUserRepo, AIProviderRepo

    email    = os.getenv("ADMIN_EMAIL",    "admin@master-chatbot.local")
    password = os.getenv("ADMIN_PASSWORD", "changeme")
    name     = os.getenv("ADMIN_NAME",     "Administrator")

    async with AsyncSessionLocal() as db:
        # Create admin user if none exists
        user_repo = AdminUserRepo(db)
        if not await user_repo.exists():
            from .crypto import hash_password
            user = await user_repo.create(
                email=email,
                password_hash=hash_password(password),
                full_name=name,
            )
            await db.commit()
            logger.info("[SEED] Admin user created: %s (id=%s)", email, user.id)
            print(f"✅  Admin user created → email: {email}")
            if password == "changeme":
                print("⚠️   Default password is 'changeme' — change it via ADMIN_PASSWORD env var!")
        else:
            logger.info("[SEED] Admin user already exists — skipping.")
            print("ℹ️   Admin user already exists — skipping.")

        # Seed default global settings
        svc = SettingsService(db)
        defaults = {
            "application_name":       "Master Chatbot",
            "environment":            os.getenv("ENVIRONMENT", "development"),
            "auto_discovery_enabled": True,
            "debug_logging_enabled":  False,
            "maintenance_mode":       False,
        }
        for k, v in defaults.items():
            existing = await svc.get(k)
            if existing is None:
                await svc.upsert(k, v)
        await db.commit()
        print("✅  Default global settings seeded.")

        # Log provider count
        provider_repo = AIProviderRepo(db)
        providers = await provider_repo.list_all()
        print(f"ℹ️   AI providers available: {[p.name for p in providers]}")

    print("\n✅  Seed complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())
