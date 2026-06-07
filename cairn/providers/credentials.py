"""Credential resolver (R18.2, R3)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cairn.providers.capabilities import get

_DEFAULT_KEY_ENVS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama-cloud": "OLLAMA_CLOUD_API_KEY",
    "groq": "GROQ_API_KEY",
    "openai-compatible": "OPENAI_API_KEY",
}

_DEFAULT_BASE_URL_ENVS: dict[str, str] = {
    "openai": "OPENAI_BASE_URL",
    "anthropic": "ANTHROPIC_BASE_URL",
    "ollama": "OLLAMA_HOST",
    "ollama-cloud": "OLLAMA_CLOUD_BASE_URL",
}


@dataclass(frozen=True)
class ResolvedCredentials:
    api_key: str | None
    base_url: str
    key_env: str | None


def _user_config() -> dict[str, Any]:
    path = Path.home() / ".config" / "cairn" / "config.toml"
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def resolve_credentials(
    provider: str,
    *,
    api_key_env: str | None = None,
    base_url_override: str | None = None,
) -> ResolvedCredentials:
    cap = get(provider)
    user_cfg = _user_config()
    provider_cfg = user_cfg.get("providers", {}).get(provider, {})

    key_env = (
        api_key_env
        or provider_cfg.get("api_key_env")
        or _DEFAULT_KEY_ENVS.get(provider)
    )
    api_key: str | None = None
    if key_env:
        api_key = os.environ.get(str(key_env)) or None

    base_url = (
        base_url_override
        or provider_cfg.get("base_url")
        or (
            os.environ.get(_DEFAULT_BASE_URL_ENVS[provider])
            if provider in _DEFAULT_BASE_URL_ENVS
            else None
        )
        or (cap.default_base_url if cap else "https://api.openai.com")
    )
    return ResolvedCredentials(
        api_key=api_key,
        base_url=str(base_url),
        key_env=str(key_env) if key_env else None,
    )


def require_api_key(creds: ResolvedCredentials, provider: str) -> str:
    if creds.api_key:
        return creds.api_key
    env_name = creds.key_env or _DEFAULT_KEY_ENVS.get(provider, "API_KEY")
    msg = f"Missing credential: set environment variable {env_name!r} (secrets from env only — R3)"
    raise RuntimeError(msg)
