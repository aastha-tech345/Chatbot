"""Configuration for Master Chatbot Client SDK."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class MasterChatbotConfig:
    """Configuration for Master Chatbot Client."""

    base_url: str
    app_id: str
    service_key: str
    timeout: float = 30
    retries: int = 3
    log_level: str = "INFO"
    verify_ssl: bool = True

    @classmethod
    def from_env(cls) -> MasterChatbotConfig:
        """Load configuration from environment variables.

        Required environment variables:
            MASTER_CHATBOT_URL: Base URL of Master Chatbot API
            MASTER_CHATBOT_APP_ID: Application ID (e.g., 'hrm', 'healthcare')
            MASTER_CHATBOT_SERVICE_KEY: Service account key for authentication

        Optional environment variables:
            MASTER_CHATBOT_TIMEOUT: Request timeout in seconds (default: 30)
            MASTER_CHATBOT_RETRIES: Number of retry attempts (default: 3)
            MASTER_CHATBOT_LOG_LEVEL: Logging level (default: INFO)
            MASTER_CHATBOT_VERIFY_SSL: Verify SSL certificates (default: true)
        """
        base_url = os.getenv("MASTER_CHATBOT_URL")
        app_id = os.getenv("MASTER_CHATBOT_APP_ID")
        service_key = os.getenv("MASTER_CHATBOT_SERVICE_KEY")

        if not base_url:
            raise ValueError("MASTER_CHATBOT_URL environment variable not set")
        if not app_id:
            raise ValueError("MASTER_CHATBOT_APP_ID environment variable not set")
        if not service_key:
            raise ValueError("MASTER_CHATBOT_SERVICE_KEY environment variable not set")

        try:
            timeout = float(os.getenv("MASTER_CHATBOT_TIMEOUT", "30"))
            retries = int(os.getenv("MASTER_CHATBOT_RETRIES", "3"))
        except ValueError as exc:
            raise ValueError("MASTER_CHATBOT_TIMEOUT and MASTER_CHATBOT_RETRIES must be numeric") from exc
        log_level = os.getenv("MASTER_CHATBOT_LOG_LEVEL", "INFO")
        verify_ssl = os.getenv("MASTER_CHATBOT_VERIFY_SSL", "true").lower() == "true"

        return cls(
            base_url=base_url,
            app_id=app_id,
            service_key=service_key,
            timeout=timeout,
            retries=retries,
            log_level=log_level,
            verify_ssl=verify_ssl,
        )

    def validate(self) -> None:
        """Validate configuration."""
        self.base_url = self.base_url.rstrip("/")
        parsed_url = urlparse(self.base_url)
        if not self.base_url or parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("base_url is required")
        if not self.app_id or not self.app_id.replace("_", "").replace("-", "").isalnum():
            raise ValueError("app_id is required")
        if not self.service_key:
            raise ValueError("service_key is required")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.retries < 0:
            raise ValueError("retries must be non-negative")

    @property
    def chat_url(self) -> str:
        """Return the canonical chat endpoint for either supported base URL form."""
        base_url = self.base_url.rstrip("/")
        if base_url.endswith("/api/v1"):
            return f"{base_url}/chat"
        return f"{base_url}/api/v1/chat"
