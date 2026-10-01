from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


SERVICE_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file() -> None:
    """Load local service settings without ever overwriting deployment variables."""
    env_file = SERVICE_ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


@dataclass(frozen=True, slots=True)
class ApplicationSettings:
    app_id: str
    api_url: str
    jwt_secret: str
    service_key: str
    jwt_algorithm: str = "HS256"

    @property
    def configured(self) -> bool:
        return bool(self.api_url and self.jwt_secret and self.service_key)


def _application_settings(app_id: str) -> ApplicationSettings:
    prefix = app_id.upper()
    return ApplicationSettings(
        app_id=app_id,
        api_url=os.getenv(f"{prefix}_API_URL", "").rstrip("/"),
        jwt_secret=os.getenv(f"{prefix}_JWT_SECRET", ""),
        service_key=os.getenv(f"{prefix}_MASTER_CHATBOT_SERVICE_KEY", ""),
        jwt_algorithm=os.getenv(f"{prefix}_JWT_ALGORITHM", "HS256"),
    )


APPLICATIONS = {app_id: _application_settings(app_id) for app_id in ("ecommerce", "hrm", "his")}
MAX_RESULT_ITEMS = int(os.getenv("MASTER_CHATBOT_MAX_RESULT_ITEMS", "25"))
