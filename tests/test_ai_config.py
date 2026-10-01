import asyncio
import sys

import httpx

sys.path.insert(0, "chatbot/backend")

from app.ai_config import AIConfigManager
from app.main import app


async def _request(transport: httpx.ASGITransport, method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def test_ai_config_manager_updates_only_managed_env_values(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# keep this",
                "DATABASE_URL=postgres://example",
                "AI_PROVIDER=old",
                "GROQ_API_KEY=old-key",
                "GROQ_API_KEY=duplicate-key",
                "GROQ_MODEL='old model'",
                "STRIPE_SECRET_KEY=sk_test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)

    manager = AIConfigManager(env_path)
    config = manager.update(ai_provider=" groq ", groq_api_key=' gsk_new"key ', groq_model=" openai/gpt-oss-20b ")

    assert config.ai_provider == "groq"
    assert config.groq_api_key == 'gsk_new"key'
    assert config.groq_model == "openai/gpt-oss-20b"
    saved = env_path.read_text(encoding="utf-8")
    assert "# keep this" in saved
    assert "DATABASE_URL=postgres://example" in saved
    assert "STRIPE_SECRET_KEY=sk_test" in saved
    assert saved.count("GROQ_API_KEY=") == 1
    assert 'GROQ_API_KEY="gsk_new\\"key"' in saved
    assert 'GROQ_MODEL="openai/gpt-oss-20b"' in saved


def test_ai_config_public_view_masks_secret(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_1234567890abcd")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")

    body = AIConfigManager().current().public_dict()

    assert body == {
        "ai_provider": "groq",
        "groq_api_key_configured": True,
        "groq_api_key_masked": "************abcd",
        "groq_model": "openai/gpt-oss-20b",
    }


def test_ai_config_endpoint_is_protected(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("MASTER_CHATBOT_CONFIG_KEY", "config-key")

    response = asyncio.run(_request(httpx.ASGITransport(app=app), "GET", "/api/v1/config/ai"))

    assert response.status_code == 403


def test_ai_config_endpoint_updates_runtime_and_masks_response(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    from app import main

    manager = AIConfigManager(tmp_path / ".env")
    monkeypatch.setattr(main, "ai_config_manager", manager)
    monkeypatch.setenv("MASTER_CHATBOT_CONFIG_KEY", "config-key")

    response = asyncio.run(
        _request(
            httpx.ASGITransport(app=app),
            "PUT",
            "/api/v1/config/ai",
            headers={"X-Master-Chatbot-Config-Key": "config-key"},
            json={"ai_provider": "groq", "groq_api_key": "gsk_secretabcd", "groq_model": "openai/gpt-oss-20b"},
        )
    )

    assert response.status_code == 200
    body = response.json()
    assert body["groq_api_key_configured"] is True
    assert body["groq_api_key_masked"] == "************abcd"
    assert "gsk_secretabcd" not in response.text
    assert manager.current().groq_api_key == "gsk_secretabcd"
