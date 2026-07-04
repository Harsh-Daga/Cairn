"""Adapter protocol: detect / iter_new / to_spans (Phase 2)."""

from __future__ import annotations

from typing import Protocol

from server.models.trace import TraceSummary


class Adapter(Protocol):
    """Ingest adapter interface."""

    adapter_id: str

    def detect(self) -> list[str]:
        """Return stream references for this adapter."""
        ...

    def to_spans(self, raw: bytes) -> tuple[TraceSummary, list[object]]:
        """Parse raw bytes into trace and spans."""
        ...
