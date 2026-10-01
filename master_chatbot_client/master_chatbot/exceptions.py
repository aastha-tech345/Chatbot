"""Exception classes for Master Chatbot Client SDK."""

from __future__ import annotations


class MasterChatbotError(Exception):
    """Base exception for all Master Chatbot SDK errors."""

    pass


class MasterChatbotConfigError(MasterChatbotError):
    """Raised when SDK configuration is invalid."""

    pass


class MasterChatbotValidationError(MasterChatbotError):
    """Raised when request validation fails (bad app_id, message too long, etc.)."""

    pass


class MasterChatbotAuthenticationError(MasterChatbotError):
    """Raised when authentication fails (invalid/expired JWT token)."""

    pass


class MasterChatbotAuthorizationError(MasterChatbotError):
    """Raised when user lacks permission for requested action."""

    pass


class MasterChatbotTimeoutError(MasterChatbotError):
    """Raised when request exceeds timeout."""

    pass


class MasterChatbotRateLimitError(MasterChatbotError):
    """Raised when rate limit is exceeded."""

    pass


class MasterChatbotServiceUnavailableError(MasterChatbotError):
    """Raised when Master Chatbot service is unavailable."""

    pass


class MasterChatbotAPIError(MasterChatbotError):
    """Raised for other API errors (5xx, network errors, etc.)."""

    def __init__(self, message: str, status_code: int | None = None, details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}
