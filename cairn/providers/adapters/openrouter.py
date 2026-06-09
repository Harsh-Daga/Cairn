"""OpenRouter OpenAI-compatible adapter helpers."""

from __future__ import annotations

OPENROUTER_BASE_URL = "https://openrouter.ai/api"


def openrouter_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/cairn-project/cairn",
        "X-Title": "Cairn",
    }
