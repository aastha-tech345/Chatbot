"""Internal helpers that keep credentials and payloads out of SDK logs."""

from __future__ import annotations

import uuid


def normalize_bearer_token(token: str) -> str:
    """Return an Authorization value without ever logging the token."""
    token = token.strip()
    if not token:
        raise ValueError("user_jwt_token is required")
    return token if token.lower().startswith("bearer ") else f"Bearer {token}"


def build_headers(
    *,
    user_jwt_token: str,
    service_key: str,
    request_id: str,
    session_id: str | None,
) -> dict[str, str]:
    if not service_key:
        raise ValueError("service_key is required")
    headers = {
        "Authorization": normalize_bearer_token(user_jwt_token),
        "Content-Type": "application/json",
        "X-Master-Chatbot-Service-Key": service_key,
        "X-Request-Id": request_id,
    }
    if session_id:
        headers["X-Chat-Session-Id"] = session_id
    return headers


def new_request_id(request_id: str | None) -> str:
    return request_id or str(uuid.uuid4())
