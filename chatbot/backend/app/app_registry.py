from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import HTTPException, status

from .models import ApplicationDefinition, RouteDefinition


SERVICE_ROOT = Path(__file__).resolve().parents[2]


def _load_env_file() -> None:
    env_file = SERVICE_ROOT / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


class ApplicationRegistry:
    """Loads application contracts; no domain behavior belongs in this class."""

    def __init__(self, registry_path: Path | None = None) -> None:
        configured_path = os.getenv("MASTER_CHATBOT_REGISTRY_PATH")
        self.path = registry_path or (Path(configured_path) if configured_path else SERVICE_ROOT / "config" / "applications.json")
        self._applications = self._load()

    def _load(self) -> dict[str, ApplicationDefinition]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            items = raw["applications"]
            app_ids = [item.get("app_id") for item in items]
            if len(app_ids) != len(set(app_ids)):
                raise ValueError("Duplicate application IDs are not allowed")
            for item in items:
                base_url = item.get("base_url", "")
                if base_url.startswith("${") and base_url.endswith("}"):
                    item["base_url"] = os.getenv(base_url[2:-1], "")
            applications = [ApplicationDefinition.model_validate(item) for item in items]
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid Master Chatbot registry: {self.path}") from exc

        # Load policies for each application (fail-safe: missing policies = no actions allowed)
        from .policy_registry import load_policies
        for item, application in zip(items, applications):
            raw_policies = item.get("policies", [])
            load_policies(application.app_id, raw_policies if isinstance(raw_policies, list) else [])

        return {application.app_id: application for application in applications}

    def _read_raw(self) -> dict[str, object]:
        """Read the persisted contract without resolving environment placeholders."""
        if not self.path.is_file():
            return {"applications": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not isinstance(raw.get("applications"), list):
                raise ValueError("applications must be a list")
            return raw
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid Master Chatbot registry: {self.path}") from exc

    def _write_raw(self, raw: dict[str, object]) -> None:
        """Atomically replace the file only after its application schemas validate."""
        applications = raw.get("applications")
        if not isinstance(applications, list):
            raise RuntimeError("Invalid Master Chatbot registry applications")
        app_ids = [item.get("app_id") for item in applications if isinstance(item, dict)]
        if len(app_ids) != len(applications) or len(app_ids) != len(set(app_ids)):
            raise RuntimeError("Duplicate or invalid application IDs are not allowed")
        try:
            [ApplicationDefinition.model_validate(item) for item in applications]
        except ValueError as exc:
            raise RuntimeError("Invalid Master Chatbot application definition") from exc

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as temp:
            json.dump(raw, temp, indent=2)
            temp.write("\n")
            temp_path = Path(temp.name)
        temp_path.replace(self.path)
        self._applications = self._load()

    def upsert(self, application: ApplicationDefinition) -> ApplicationDefinition:
        """Create or replace one application while preserving all other contracts."""
        raw = self._read_raw()
        applications = raw["applications"]
        assert isinstance(applications, list)
        serialized = application.model_dump(mode="json")
        raw["applications"] = [
            serialized if item.get("app_id") == application.app_id else item
            for item in applications
            if isinstance(item, dict)
        ]
        if not any(item.get("app_id") == application.app_id for item in applications if isinstance(item, dict)):
            raw["applications"].append(serialized)
        self._write_raw(raw)
        return self.get(application.app_id)

    def update_routes(self, app_id: str, routes: list[RouteDefinition]) -> ApplicationDefinition:
        """Replace only one application's routes after validating the complete contract."""
        existing = self.get(app_id)
        return self.upsert(existing.model_copy(update={"routes": routes}))

    def unregister(self, app_id: str) -> None:
        """Remove one application without modifying the remaining registry."""
        raw = self._read_raw()
        applications = raw["applications"]
        assert isinstance(applications, list)
        retained = [item for item in applications if isinstance(item, dict) and item.get("app_id") != app_id]
        if len(retained) == len(applications):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application is not registered")
        raw["applications"] = retained
        self._write_raw(raw)

    def status(self, app_id: str) -> dict[str, object]:
        application = self.get(app_id)
        return {
            "app_id": application.app_id,
            "name": application.name,
            "base_url": application.base_url,
            "enabled": bool(application.base_url),
            "route_count": len(application.routes),
        }

    def get(self, app_id: str) -> ApplicationDefinition:
        application = self._applications.get(app_id)
        if application is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown or unregistered application")
        return application

    def route(self, application: ApplicationDefinition, route_name: str) -> RouteDefinition:
        for route in application.routes:
            if route.name == route_name:
                return route
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The selected route is not registered for this application")


application_registry = ApplicationRegistry()
