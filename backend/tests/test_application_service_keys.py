"""Service-key registration lifecycle using a disposable database and real APIs."""
import asyncio
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import main
from app.admin_auth import require_admin
from app.app_registry import application_registry
from app.crypto import decrypt
from app.database import Base, get_db
from app.db_models import ApplicationCredential, AuditLog


def test_service_key_lifecycle(monkeypatch, caplog):
    monkeypatch.setenv("SECRET_KEY", "test-only-encryption-key-32-bytes!")
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(application_registry, "_applications", {})
    monkeypatch.setattr(application_registry, "_credentials", {})

    async def workflow(state):
        assert "service_key" not in state
        assert "test-only-first-key" not in repr(state)
        return {"response_message": "OK", "data": [], "metadata": {}}

    monkeypatch.setattr(main.workflow, "run", workflow)

    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        # Existing models declare some indexes twice; create the tables individually.
        async with engine.begin() as conn:
            from sqlalchemy.schema import CreateTable
            for table in Base.metadata.sorted_tables:
                await conn.execute(CreateTable(table))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr("app.database.AsyncSessionLocal", sessions)

        async def db_override():
            async with sessions() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        main.app.dependency_overrides[get_db] = db_override
        main.app.dependency_overrides[require_admin] = lambda: None
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="https://test") as client:
                base = "/api/v1/admin/applications"
                payload = {"name": "Example", "app_id": "key_test", "base_url": "https://example.test", "discovery_mode": "manual", "auth_type": "service_key", "service_key": "test-only-first-key"}
                response = await client.post(base, json=payload)
                assert response.status_code == 201, response.text
                data = response.json()
                uid = data["id"]
                assert data["service_key_configured"] is True
                assert "service_key" not in data
                assert "encrypted" not in response.text
                assert payload["service_key"] not in response.text
                assert application_registry.get_service_key("key_test") == payload["service_key"]
                async with sessions() as db:
                    rows = (await db.execute(select(ApplicationCredential))).scalars().all()
                    assert len(rows) == 1
                    credential_id = rows[0].id
                    assert rows[0].application_id == uid
                    assert rows[0].auth_type == "service_key" and rows[0].is_active
                    assert rows[0].bearer_token_encrypted != payload["service_key"]
                    assert decrypt(rows[0].bearer_token_encrypted) == payload["service_key"]

                for key, expected in [(None, 403), ("wrong", 403), (payload["service_key"], 200)]:
                    headers = {"X-Master-Chatbot-Service-Key": key} if key else {}
                    chat = await client.post("/api/v1/chat", json={"app_id": "key_test", "message": "hello"}, headers=headers)
                    assert chat.status_code == expected, chat.text

                updated = await client.put(f"{base}/{uid}", json={"service_key": "test-only-rotated-key"})
                assert updated.status_code == 200
                for edit in [{"name": "Renamed"}, {"service_key": ""}, {"service_key": None}, {"service_key": "   "}]:
                    assert (await client.put(f"{base}/{uid}", json=edit)).status_code == 200
                    assert application_registry.get_service_key("key_test") == "test-only-rotated-key"
                for key, expected in [("test-only-first-key", 403), ("test-only-rotated-key", 200)]:
                    chat = await client.post("/api/v1/chat", json={"app_id": "key_test", "message": "hello"}, headers={"X-Master-Chatbot-Service-Key": key})
                    assert chat.status_code == expected
                for path in [base, f"{base}/{uid}"]:
                    response = await client.get(path)
                    assert "test-only-" not in response.text
                    assert "bearer_token_encrypted" not in response.text
                async with sessions() as db:
                    rows = (await db.execute(select(ApplicationCredential))).scalars().all()
                    assert len(rows) == 1 and rows[0].id == credential_id
                    assert decrypt(rows[0].bearer_token_encrypted) == "test-only-rotated-key"
                    audits = (await db.execute(select(AuditLog))).scalars().all()
                    assert "test-only-" not in repr([a.__dict__ for a in audits])

                await client.put(f"{base}/{uid}", json={"status": "inactive"})
                assert application_registry.get_service_key("key_test") == ""
                await client.put(f"{base}/{uid}", json={"status": "active"})
                assert application_registry.get_service_key("key_test") == "test-only-rotated-key"
                await client.put(f"{base}/{uid}", json={"app_id": "renamed_app"})
                assert application_registry.get_service_key("key_test") == ""
                assert application_registry.get_service_key("renamed_app") == "test-only-rotated-key"

                optional = await client.post(base, json={"name": "Optional", "app_id": "optional", "base_url": "https://example.test", "discovery_mode": "manual"})
                assert optional.status_code == 201
                assert optional.json()["service_key_configured"] is False
                required = await client.post(base, json={**payload, "app_id": "required", "service_key": " "})
                assert required.status_code == 422
                invalid = await client.post(base, json={**payload, "name": ""})
                assert invalid.status_code == 422
                assert "test-only-first-key" not in invalid.text
                assert (await client.delete(f"{base}/{uid}")).status_code == 200
                assert application_registry.get_service_key("renamed_app") == ""
                async with sessions() as db:
                    assert not (await db.execute(select(ApplicationCredential))).scalars().all()
        finally:
            main.app.dependency_overrides.clear()
            await engine.dispose()

    async def bounded_run():
        await asyncio.wait_for(run(), timeout=20)

    asyncio.run(bounded_run())
    assert "test-only-first-key" not in caplog.text
    assert "test-only-rotated-key" not in caplog.text
