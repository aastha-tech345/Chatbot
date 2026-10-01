"""
Credential encryption and password hashing.

Encryption key:  SECRET_KEY env var (must be 32 URL-safe base64 bytes for Fernet).
If SECRET_KEY is absent a deterministic dev key is used — NEVER in production.

SECURITY RULES:
- Never log plaintext keys, tokens, or passwords.
- Never return raw decrypted credentials outside this module unless building a
  configuration struct that only the LLM factory needs.
- Frontend always receives masked values only.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from typing import Optional

import bcrypt

# ── Password hashing ────────────────────────────────────────────────────────

def _password_bytes(plain: str) -> bytes:
    # Preserve Passlib bcrypt semantics for existing passwords, including its
    # 72-byte truncation. bcrypt 5 otherwise rejects these legacy inputs.
    if "\0" in plain:
        raise ValueError("Passwords cannot contain null bytes")
    return plain.encode("utf-8")[:72]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_password_bytes(plain), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(plain), hashed.encode("ascii"))
    except (ValueError, UnicodeError):
        return False


# ── Symmetric encryption for stored credentials ─────────────────────────────

def _get_fernet():
    """Lazy-import Fernet and build the cipher from SECRET_KEY."""
    from cryptography.fernet import Fernet
    raw = os.getenv("SECRET_KEY", "")
    if raw:
        # Accept both raw 32-byte keys and already-encoded Fernet keys
        key = raw.encode() if len(raw) == 44 else base64.urlsafe_b64encode(raw.encode()[:32].ljust(32, b"\0"))
    else:
        # Deterministic dev key — log a loud warning
        import logging
        logging.getLogger(__name__).warning(
            "[CRYPTO] SECRET_KEY not set — using insecure dev key. Set SECRET_KEY in production!"
        )
        seed = b"master-chatbot-dev-key-insecure!"
        key = base64.urlsafe_b64encode(seed)
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Return a URL-safe base64 Fernet token (string)."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet token and return the plaintext string."""
    return _get_fernet().decrypt(token.encode()).decode()


def mask(plaintext: str, show_last: int = 4) -> str:
    """Return a masked representation safe for frontend display."""
    if not plaintext:
        return ""
    visible = plaintext[-show_last:] if len(plaintext) >= show_last else plaintext
    return f"{'*' * 12}{visible}"


# ── JWT helpers for admin authentication ────────────────────────────────────

def _jwt_secret() -> str:
    s = os.getenv("JWT_SECRET_KEY", os.getenv("SECRET_KEY", ""))
    if not s:
        import logging
        logging.getLogger(__name__).warning("[CRYPTO] JWT_SECRET_KEY not set — using insecure default!")
        return "master-chatbot-insecure-jwt-secret"
    return s


def create_access_token(data: dict, expires_seconds: int = 3600) -> str:
    import time, json, hmac as _hmac, hashlib as _hs
    payload = {**data, "exp": int(time.time()) + expires_seconds, "iat": int(time.time())}
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    body   = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    sig_bytes = _hmac.new(_jwt_secret().encode(), f"{header}.{body}".encode(), _hs.sha256).digest()
    sig    = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()
    return f"{header}.{body}.{sig}"


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
