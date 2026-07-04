"""Canonical JSON hashing primitives."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from typing import Any


class CanonicalError(ValueError):
    """Raised when a value cannot be canonically encoded."""


def _normalize_float(value: float) -> str:
    if math.isnan(value) or math.isinf(value):
        msg = f"non-finite float cannot be hashed: {value!r}"
        raise CanonicalError(msg)
    text = format(value, ".15g")
    return "0" if text in {"-0", "-0.0"} else text


def _canonicalize(obj: Any) -> Any:
    if obj is None or isinstance(obj, bool):
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return _normalize_float(obj)
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, bytes):
        msg = "bytes must be hashed raw via hash_bytes(), not embedded in canonical JSON"
        raise CanonicalError(msg)
    if isinstance(obj, list):
        return [_canonicalize(item) for item in obj]
    if isinstance(obj, dict):
        return {
            unicodedata.normalize("NFC", str(key)): _canonicalize(value)
            for key, value in sorted(obj.items(), key=lambda pair: str(pair[0]))
        }
    msg = f"unsupported type for canonical JSON: {type(obj).__name__}"
    raise CanonicalError(msg)


def canonical_json(obj: Any) -> str:
    """Deterministic JSON for hashing."""
    return json.dumps(_canonicalize(obj), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def hash_bytes(data: bytes) -> str:
    """SHA-256 of raw bytes, lowercase hex."""
    return hashlib.sha256(data).hexdigest()


def hash_obj(obj: Any) -> str:
    """SHA-256 of canonical JSON."""
    return hash_bytes(canonical_json(obj).encode("utf-8"))
