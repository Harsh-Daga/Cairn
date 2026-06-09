"""Access control helpers for collaboration sync bundles."""

from __future__ import annotations

import hashlib
import secrets


def hash_access_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_access_token() -> str:
    return secrets.token_urlsafe(32)


def verify_access_token(token: str, expected_hash: str | None) -> bool:
    if expected_hash is None:
        return True
    return hash_access_token(token) == expected_hash
