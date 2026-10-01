"""Remove credentials from API results, retained context and model inputs."""
import re
from typing import Any

_SECRET = re.compile(r"password|passwd|token|secret|authorization|cookie|api.?key|otp", re.I)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.I)
_CREDENTIAL = re.compile(r'(password|passwd|access_token|refresh_token|secret|otp)([\s"\x27]*[:=][\s"\x27]*)([^\s,}"\x27]+)', re.I)


def safe_text(value: str) -> str:
    return _CREDENTIAL.sub(r"\1\2[REDACTED]", _BEARER.sub("[REDACTED]", value))


def safe_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: safe_data(item) for key, item in value.items() if not _SECRET.search(str(key))}
    if isinstance(value, list):
        return [safe_data(item) for item in value]
    return safe_text(value) if isinstance(value, str) else value
