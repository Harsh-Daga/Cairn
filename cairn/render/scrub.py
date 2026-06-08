"""Redact secrets from bundle display payloads (R16, §11.8)."""

from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"sk-ant-[a-zA-Z0-9\-_]{20,}"),
    re.compile(r"ghp_[a-zA-Z0-9]{20,}"),
    re.compile(r"gho_[a-zA-Z0-9]{20,}"),
    re.compile(r"xox[baprs]-[a-zA-Z0-9\-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)api[_-]?key['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{16,}"),
    re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)

_REDACTED = "[REDACTED]"


def scrub_text(text: str) -> str:
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(_REDACTED, out)
    return out


def scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, list):
        return [scrub_value(item) for item in value]
    if isinstance(value, dict):
        return {key: scrub_value(item) for key, item in value.items()}
    return value
