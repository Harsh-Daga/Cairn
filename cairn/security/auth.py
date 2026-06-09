"""Optional bearer-token auth for local HTTP services."""

from __future__ import annotations

import hmac
import os


def api_token_from_env() -> str | None:
    token = os.environ.get("CAIRN_API_TOKEN")
    if token is None or not token.strip():
        return None
    return token.strip()


def authorize_bearer(authorization: str | None, required_token: str | None) -> bool:
    """Return True when no token is configured or the bearer token matches."""
    if required_token is None:
        return True
    if not authorization or not authorization.startswith("Bearer "):
        return False
    provided = authorization.removeprefix("Bearer ").strip()
    return hmac.compare_digest(provided, required_token)
