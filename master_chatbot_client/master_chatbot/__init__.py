"""Master Chatbot Client SDK for multi-application AI assistant integration.

This SDK provides a simple interface for external applications (HRM, Healthcare, Finance, etc.)
to integrate with the centralized Master Chatbot Service without embedding chatbot logic
into their own codebase.

Usage:
    >>> from master_chatbot import MasterChatbotClient
    >>> client = MasterChatbotClient.from_env()
    >>> response = await client.achat(
    ...     message="Show my profile",
    ...     user_jwt_token=user_jwt,
    ... )
    >>> print(response.message)
"""

from master_chatbot.async_client import AsyncMasterChatbotClient
from master_chatbot.client import MasterChatbotClient
from master_chatbot.config import MasterChatbotConfig
from master_chatbot.exceptions import (
    MasterChatbotAPIError,
    MasterChatbotAuthenticationError,
    MasterChatbotAuthorizationError,
    MasterChatbotConfigError,
    MasterChatbotError,
    MasterChatbotRateLimitError,
    MasterChatbotServiceUnavailableError,
    MasterChatbotTimeoutError,
    MasterChatbotValidationError,
)
from master_chatbot.models import ChatRequest, ChatResponse, UserContext

__version__ = "1.0.0"

__all__ = [
    "MasterChatbotClient",
    "AsyncMasterChatbotClient",
    "MasterChatbotConfig",
    "ChatRequest",
    "ChatResponse",
    "UserContext",
    "MasterChatbotError",
    "MasterChatbotConfigError",
    "MasterChatbotValidationError",
    "MasterChatbotAuthenticationError",
    "MasterChatbotAuthorizationError",
    "MasterChatbotTimeoutError",
    "MasterChatbotRateLimitError",
    "MasterChatbotServiceUnavailableError",
    "MasterChatbotAPIError",
]
