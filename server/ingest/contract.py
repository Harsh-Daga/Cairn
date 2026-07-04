"""Ingest adapter protocol and types."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from server.ingest.map import ParsedSession, session_to_trace_spans
from server.models.data_quality import DataQuality
from server.models.span import Span
from server.models.trace import Trace


@dataclass(frozen=True)
class StreamRef:
    """Identifies one ingest stream (usually a file path)."""

    source: str
    stream: str
    path: Path


@dataclass(frozen=True)
class IngestCursor:
    """Incremental read position for a stream."""

    offset: int = 0
    mtime_ns: int | None = None
    size: int | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "offset": self.offset,
            "mtime_ns": self.mtime_ns,
            "size": self.size,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> IngestCursor:
        return cls(
            offset=int(data.get("offset", 0)),
            mtime_ns=int(data["mtime_ns"]) if data.get("mtime_ns") is not None else None,
            size=int(data["size"]) if data.get("size") is not None else None,
        )


class Adapter(Protocol):
    """Ingest adapter interface."""

    adapter_id: str

    def detect(self) -> list[StreamRef]:
        """Return stream references for this adapter."""
        ...

    def iter_new(
        self, cursor: IngestCursor, raw: bytes
    ) -> tuple[list[ParsedSession], IngestCursor]:
        """Parse incremental content; return sessions and updated cursor."""
        ...

    def parse_path(self, path: Path) -> ParsedSession | None:
        """Parse a session file into normalized form."""
        ...

    def to_spans(
        self,
        parsed: ParsedSession,
        *,
        workspace_id: str,
        repo_root: Path,
    ) -> tuple[Trace, list[Span], DataQuality]:
        """Map parsed session to trace/spans/quality."""
        ...


def default_to_spans(
    parsed: ParsedSession,
    *,
    workspace_id: str,
    repo_root: Path,
    pricing_overrides: dict[str, dict[str, object]] | None = None,
) -> tuple[Trace, list[Span], DataQuality]:
    return session_to_trace_spans(
        parsed,
        workspace_id=workspace_id,
        repo_root=repo_root,
        pricing_overrides=pricing_overrides,
    )


def cursor_for_file(path: Path) -> IngestCursor:
    stat = path.stat()
    return IngestCursor(offset=stat.st_size, mtime_ns=stat.st_mtime_ns, size=stat.st_size)


def read_cursor(raw: bytes) -> IngestCursor:
    if not raw:
        return IngestCursor()
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, dict):
        return IngestCursor.from_json(data)
    return IngestCursor()
