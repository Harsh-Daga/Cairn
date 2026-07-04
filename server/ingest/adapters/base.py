"""Shared adapter base helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from server.ingest.adapters.claude_code import ToolCallDraft
from server.ingest.contract import IngestCursor, StreamRef, cursor_for_file, default_to_spans
from server.ingest.map import ParsedSession, normalize_source
from server.ingest.usage import ObservedUsage
from server.models.data_quality import DataQuality
from server.models.span import Span
from server.models.trace import Trace


class FileAdapterBase:
    """Base for file-based ingest adapters."""

    adapter_id: str
    legacy_source: str

    def __init__(self, workspace_root: Path, workspace_id: str) -> None:
        self.workspace_root = workspace_root.resolve()
        self.workspace_id = workspace_id

    def detect(self) -> list[StreamRef]:
        paths = self._discover()
        source = normalize_source(self.legacy_source)
        return [StreamRef(source=source, stream=str(p), path=p) for p in paths]

    def iter_new(
        self, cursor: IngestCursor, raw: bytes
    ) -> tuple[list[ParsedSession], IngestCursor]:
        path = Path(raw.decode("utf-8"))
        parsed = self.parse_path(path)
        new_cursor = cursor_for_file(path)
        if parsed is None:
            return [], new_cursor
        return [parsed], new_cursor

    def to_spans(
        self,
        parsed: ParsedSession,
        *,
        workspace_id: str,
        repo_root: Path,
    ) -> tuple[Trace, list[Span], DataQuality]:
        return default_to_spans(parsed, workspace_id=workspace_id, repo_root=repo_root)

    def _discover(self) -> list[Path]:
        raise NotImplementedError

    def parse_path(self, path: Path) -> ParsedSession | None:
        raise NotImplementedError


def _parsed_from_generic(
    *,
    source: str,
    external_id: str,
    cwd: str | None,
    git_branch: str | None,
    started_at: str | None,
    ended_at: str | None,
    model: str | None,
    events: list[dict[str, Any]],
    tool_calls: list[ToolCallDraft],
    usage: ObservedUsage,
    has_cost: bool | None = None,
    status: str = "completed",
    context_window: int | None = None,
) -> ParsedSession:
    return ParsedSession(
        source=source,
        external_id=external_id,
        cwd=cwd,
        git_branch=git_branch,
        started_at=started_at,
        ended_at=ended_at,
        model=model,
        events=events,
        tool_calls=tool_calls,
        usage=usage,
        has_cost=has_cost,
        status=status,
        context_window=context_window,
    )


class LegacyParsedSession(Protocol):
    """Common shape returned by ported parser modules."""

    external_id: str
    events: list[dict[str, Any]]
    tool_calls: list[ToolCallDraft]


def _wrap_parse(
    source: str,
    parsed: LegacyParsedSession | None,
    *,
    usage_attr: str = "usage",
    has_cost: bool | None = None,
) -> ParsedSession | None:
    if parsed is None:
        return None
    usage_obj = getattr(parsed, usage_attr)
    observed = usage_obj.usage if hasattr(usage_obj, "usage") else usage_obj
    return _parsed_from_generic(
        source=source,
        external_id=str(parsed.external_id),
        cwd=getattr(parsed, "cwd", None),
        git_branch=getattr(parsed, "git_branch", None),
        started_at=getattr(parsed, "started_at", None),
        ended_at=getattr(parsed, "ended_at", None),
        model=getattr(parsed, "model", None),
        events=list(parsed.events),
        tool_calls=list(parsed.tool_calls),
        usage=observed,
        has_cost=has_cost if has_cost is not None else getattr(parsed, "has_cost", None),
        status=getattr(parsed, "status", "completed"),
        context_window=getattr(parsed, "context_window", None),
    )
