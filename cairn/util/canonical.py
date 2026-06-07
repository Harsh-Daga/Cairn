"""Canonical JSON serialization and hashing (R1, §9)."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from typing import Any

CAIRN_KEY_VERSION = 1


class CanonicalError(ValueError):
    """Raised when a value cannot be canonically encoded."""


def _normalize_float(value: float) -> str:
    if math.isnan(value) or math.isinf(value):
        msg = f"non-finite float cannot be hashed: {value!r}"
        raise CanonicalError(msg)
    text = format(value, ".15g")
    if text in {"-0", "-0.0"}:
        return "0"
    return text


def _normalize_string(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _canonicalize(obj: Any) -> Any:
    if obj is None or isinstance(obj, bool):
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return _normalize_float(obj)
    if isinstance(obj, str):
        return _normalize_string(obj)
    if isinstance(obj, bytes):
        msg = "bytes must be hashed raw via hash_bytes(), not embedded in canonical JSON"
        raise CanonicalError(msg)
    if isinstance(obj, list):
        return [_canonicalize(item) for item in obj]
    if isinstance(obj, dict):
        return {
            _normalize_string(str(key)): _canonicalize(value)
            for key, value in sorted(obj.items(), key=lambda pair: str(pair[0]))
        }
    msg = f"unsupported type for canonical JSON: {type(obj).__name__}"
    raise CanonicalError(msg)


def canonical_json(obj: Any) -> str:
    """Return deterministic JSON for hashing."""
    normalized = _canonicalize(obj)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def hash_bytes(data: bytes) -> str:
    """SHA-256 of raw bytes, lowercase hex (R1)."""
    return hashlib.sha256(data).hexdigest()


def hash_obj(obj: Any) -> str:
    """SHA-256 of canonical JSON (R1 helper h())."""
    return hash_bytes(canonical_json(obj).encode("utf-8"))


def merkle_hash(*digests: str) -> str:
    """Roll up content hashes in sorted order (§9, ADR 0006).

    Input sets are order-independent. Order-sensitive dependencies must encode
    order inside individual digests, not rely on argument order here.
    """
    if not digests:
        return hash_bytes(b"")
    ordered = sorted(digests)
    payload = canonical_json(ordered)
    return hash_bytes(payload.encode("utf-8"))
