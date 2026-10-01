"""Low-level asynchronous HTTP transport for the Master Chatbot API."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from master_chatbot.config import MasterChatbotConfig
from master_chatbot.exceptions import (
    MasterChatbotAPIError,
    MasterChatbotAuthenticationError,
    MasterChatbotAuthorizationError,
    MasterChatbotRateLimitError,
    MasterChatbotServiceUnavailableError,
    MasterChatbotTimeoutError,
    MasterChatbotValidationError,
)
from master_chatbot.models import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
_TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
_SENSITIVE_KEYS = {"authorization", "api_key", "service_key", "token", "secret", "password"}


def _safe_response_body(response: httpx.Response) -> object:
    try:
        body = response.json()
    except ValueError:
        return response.text[:2000]
    if not isinstance(body, dict):
        return body
    return {
        key: "[REDACTED]" if key.lower() in _SENSITIVE_KEYS else value
        for key, value in body.items()
    }


def raise_for_response(response: httpx.Response) -> None:
    """Map the documented API errors without logging response contents."""
    try:
        detail = response.json().get("detail", response.text)
    except Exception:
        detail = response.text or f"HTTP {response.status_code}"

    mapping = {
        400: MasterChatbotValidationError,
        401: MasterChatbotAuthenticationError,
        403: MasterChatbotAuthorizationError,
        404: MasterChatbotValidationError,
        429: MasterChatbotRateLimitError,
        500: MasterChatbotServiceUnavailableError,
        502: MasterChatbotServiceUnavailableError,
        503: MasterChatbotServiceUnavailableError,
        504: MasterChatbotServiceUnavailableError,
    }
    exception_type = mapping.get(response.status_code)
    if exception_type is not None:
        raise exception_type(str(detail))
    raise MasterChatbotAPIError(str(detail), status_code=response.status_code)


class MasterChatbotHTTPClient:
    """Transport with retries only for documented transient API failures."""

    def __init__(self, config: MasterChatbotConfig):
        self.config = config

    async def post_chat(self, *, request: ChatRequest, headers: dict[str, str]) -> ChatResponse:
        url = self.config.chat_url
        max_attempts = self.config.retries
        last_timeout: Exception | None = None
        request_body = request.to_dict()
        logger.info(
            "master_chatbot_request app_id=%s target_url=%s method=POST request_id=%s fields=%s",
            request.app_id,
            url,
            headers["X-Request-Id"],
            sorted(request_body),
        )

        async with httpx.AsyncClient(verify=self.config.verify_ssl) as client:
            for attempt in range(max_attempts):
                started = time.monotonic()
                try:
                    response = await client.post(
                        url,
                        json=request_body,
                        headers=headers,
                        timeout=self.config.timeout,
                    )
                except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
                    last_timeout = exc
                    should_retry = attempt + 1 < max_attempts
                except httpx.HTTPError as exc:
                    if attempt + 1 >= max_attempts:
                        raise MasterChatbotServiceUnavailableError("Unable to reach Master Chatbot") from exc
                    should_retry = True
                else:
                    latency_ms = round((time.monotonic() - started) * 1000)
                    logger.info(
                        "master_chatbot_response app_id=%s target_url=%s method=POST request_id=%s status=%s success=%s latency_ms=%s retry=%s response_body=%s",
                        request.app_id,
                        url,
                        headers["X-Request-Id"], response.status_code, response.status_code < 400,
                        latency_ms, attempt,
                        _safe_response_body(response) if response.status_code >= 400 else "<success>",
                    )
                    if response.status_code == 200:
                        try:
                            return ChatResponse.from_dict(response.json())
                        except (TypeError, ValueError) as exc:
                            raise MasterChatbotAPIError("Invalid response from Master Chatbot", status_code=200) from exc
                    should_retry = response.status_code in _TRANSIENT_STATUSES and attempt + 1 < max_attempts
                    if not should_retry:
                        raise_for_response(response)

                if should_retry:
                    # Attempt 1 is immediate; subsequent attempts wait 1s, then 2s.
                    await asyncio.sleep(2**attempt)

        if last_timeout is not None:
            raise MasterChatbotTimeoutError("Master Chatbot request timed out") from last_timeout
        raise MasterChatbotServiceUnavailableError("Master Chatbot request failed")
