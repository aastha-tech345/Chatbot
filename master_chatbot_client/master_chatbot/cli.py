"""Secure command-line registration client for consuming applications."""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from typing import Any, Sequence

import httpx

from master_chatbot.discovery import OpenAPIDiscoveryError, discover_application_routes


class RegistrationCLIError(ValueError):
    """A configuration, discovery, or registration API failure."""


@dataclass(frozen=True)
class RegistrationConfig:
    master_url: str
    app_id: str
    service_key: str
    api_base_url: str | None
    openapi_url: str | None
    api_prefix: str | None
    jwt_secret_env: str
    jwt_algorithm: str
    registration_key: str

    @classmethod
    def from_env(cls, *, require_api_base_url: bool) -> "RegistrationConfig":
        master_url = os.getenv("MASTER_CHATBOT_URL", "").rstrip("/")
        app_id = os.getenv("MASTER_CHATBOT_APP_ID", "")
        service_key = os.getenv("MASTER_CHATBOT_SERVICE_KEY", "")
        api_base_url = os.getenv("MASTER_CHATBOT_API_BASE_URL", "").rstrip("/") or None
        registration_key = os.getenv("MASTER_CHATBOT_REGISTRATION_KEY", "")
        if not master_url:
            raise RegistrationCLIError("MASTER_CHATBOT_URL environment variable not set")
        if not app_id:
            raise RegistrationCLIError("MASTER_CHATBOT_APP_ID environment variable not set")
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", app_id):
            raise RegistrationCLIError("MASTER_CHATBOT_APP_ID is invalid")
        if not service_key:
            raise RegistrationCLIError("MASTER_CHATBOT_SERVICE_KEY environment variable not set")
        if require_api_base_url and not api_base_url:
            raise RegistrationCLIError("MASTER_CHATBOT_API_BASE_URL environment variable not set")
        if not registration_key:
            raise RegistrationCLIError("MASTER_CHATBOT_REGISTRATION_KEY environment variable not set")
        return cls(
            master_url=master_url,
            app_id=app_id,
            service_key=service_key,
            api_base_url=api_base_url,
            openapi_url=os.getenv("MASTER_CHATBOT_OPENAPI_URL", "").strip().rstrip("/") or None,
            api_prefix=os.getenv("MASTER_CHATBOT_API_PREFIX", "").strip() or None,
            jwt_secret_env=os.getenv("MASTER_CHATBOT_JWT_SECRET_ENV", "SECRET_KEY"),
            jwt_algorithm=os.getenv("MASTER_CHATBOT_JWT_ALGORITHM", "HS256"),
            registration_key=registration_key,
        )

    @property
    def registry_url(self) -> str:
        root = self.master_url.removesuffix("/api/v1")
        return f"{root}/api/v1/registry/applications"


def _headers(config: RegistrationConfig) -> dict[str, str]:
    return {"X-Master-Chatbot-Registration-Key": config.registration_key}


def _request(config: RegistrationConfig, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        response = httpx.request(method, f"{config.registry_url}{path}", headers=_headers(config), json=payload, timeout=15.0)
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RegistrationCLIError("Master Chatbot registration request failed.") from exc
    if not isinstance(result, dict):
        raise RegistrationCLIError("Master Chatbot registration response was invalid.")
    return result


def _discovered_payload(config: RegistrationConfig) -> dict[str, Any]:
    assert config.api_base_url is not None
    try:
        resolved_openapi_url, routes = discover_application_routes(
            config.api_base_url,
            openapi_url=config.openapi_url,
            api_prefix=config.api_prefix,
        )
    except OpenAPIDiscoveryError as exc:
        raise RegistrationCLIError(str(exc)) from exc
    if not routes:
        raise RegistrationCLIError(
            f"No chatbot-safe routes were discovered from {resolved_openapi_url} (HTTP 200)."
        )
    return {
        "app_id": config.app_id,
        "name": os.getenv("MASTER_CHATBOT_APP_NAME", config.app_id),
        "base_url": config.api_base_url,
        "jwt_secret_env": config.jwt_secret_env,
        "jwt_algorithm": config.jwt_algorithm,
        "service_key_env": os.getenv(
            "MASTER_CHATBOT_SERVICE_KEY_ENV",
            f"{config.app_id.upper()}_MASTER_CHATBOT_SERVICE_KEY",
        ),
        "openapi_url": resolved_openapi_url,
        "routes": routes,
    }


def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="master-chatbot")
    parser.add_argument("command", choices=("register", "unregister", "status", "sync"))
    args = parser.parse_args(argv)
    try:
        config = RegistrationConfig.from_env(require_api_base_url=args.command in {"register", "sync"})
        if args.command == "register":
            result = _request(config, "POST", "/register", _discovered_payload(config))
        elif args.command == "sync":
            payload = _discovered_payload(config)
            result = _request(config, "PUT", f"/{config.app_id}/routes", {"routes": payload["routes"]})
        elif args.command == "status":
            result = _request(config, "GET", f"/{config.app_id}")
        else:
            _request(config, "DELETE", f"/{config.app_id}")
            print(f"Application unregistered: {config.app_id}")
            return 0
    except RegistrationCLIError as exc:
        parser.error(str(exc))

    print(f"Application: {result['app_id']}")
    print(f"Name: {result['name']}")
    print(f"Base URL: {result['base_url']}")
    print(f"Enabled: {result['enabled']}")
    print(f"Route count: {result['route_count']}")
    return 0


def main() -> None:
    run()


if __name__ == "__main__":
    main()
