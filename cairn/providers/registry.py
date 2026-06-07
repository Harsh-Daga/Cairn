"""Provider factory (R5, R18)."""

from __future__ import annotations

from pathlib import Path

from cairn.providers.adapters.http import HttpProvider
from cairn.providers.capabilities import infer_provider
from cairn.providers.credentials import resolve_credentials
from cairn.providers.protocol import Provider
from cairn.providers.recorded import RecordedProvider


def create_provider(
    *,
    mode: str = "recorded",
    fixtures_dir: Path | None = None,
    provider: str | None = None,
    model: str = "gpt-4o-mini",
) -> Provider:
    if mode == "recorded":
        if fixtures_dir is None:
            msg = "fixtures_dir required for recorded provider"
            raise ValueError(msg)
        return RecordedProvider(fixtures_dir, record=False)
    resolved = provider or infer_provider(model)
    creds = resolve_credentials(resolved)
    return HttpProvider(resolved, creds)
