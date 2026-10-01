"""
Bootstrap / infrastructure configuration.

Only infrastructure and security variables are loaded here.
Application runtime configuration (URLs, secrets, credentials) comes from
the database via ApplicationRegistry.

.env variables that REMAIN here (infrastructure/bootstrap):
  - DATABASE_URL
  - SECRET_KEY / JWT_SECRET_KEY
  - HOST, PORT
  - CORS_ORIGINS
  - MASTER_CHATBOT_REGISTRATION_KEY
  - MASTER_CHATBOT_CONFIG_KEY
  - ACCESS_TOKEN_EXPIRE_SECONDS
  - REFRESH_TOKEN_EXPIRE_SECONDS
  - MASTER_CHATBOT_MAX_RESULT_ITEMS

.env variables that are NO LONGER read at runtime (DB is source of truth):
  - AI_PROVIDER       → ai_credentials table (is_active=True)
  - GROQ_API_KEY      → ai_credentials.api_key_encrypted
  - GROQ_MODEL        → ai_credentials.model
  - HIS_API_URL       → applications.base_url
  - HIS_JWT_SECRET    → application_credentials (auth_type=jwt)
  - HIS_MASTER_CHATBOT_SERVICE_KEY → application_credentials (auth_type=service_key)
  - ECOMMERCE_*       → same as above
"""
from __future__ import annotations

import os
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file() -> None:
    """Load local service settings without ever overwriting deployment variables."""
    for env_file in (SERVICE_ROOT / "backend" / ".env", SERVICE_ROOT / ".env"):
        if not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


# Infrastructure constants (safe to read from env)
MAX_RESULT_ITEMS = int(os.getenv("MASTER_CHATBOT_MAX_RESULT_ITEMS", "25"))

# NOTE: The legacy APPLICATIONS dict that read {APP}_API_URL, {APP}_JWT_SECRET,
# etc. has been removed. All application runtime config comes from the DB.
# See app/app_registry.py and app/migrations/import_runtime_config.py.
