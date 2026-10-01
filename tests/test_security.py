import base64
import hashlib
import hmac
import json
import sys
import time

from fastapi import HTTPException

sys.path.insert(0, "chatbot/backend")
from app.security import verify_hs256_jwt


def _token(secret: str) -> str:
    def part(value: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    header, payload = part({"alg": "HS256"}), part({"sub": "user-1", "exp": time.time() + 60})
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{header}.{payload}.{signature}"


def test_valid_token_is_verified() -> None:
    claims = verify_hs256_jwt(f"Bearer {_token('secret')}", secret="secret", algorithm="HS256")
    assert claims["sub"] == "user-1"


def test_invalid_signature_is_rejected() -> None:
    try:
        verify_hs256_jwt(f"Bearer {_token('other')}", secret="secret", algorithm="HS256")
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("invalid token was accepted")
