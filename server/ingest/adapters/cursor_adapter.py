"""Cursor adapter."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.base import FileAdapterBase, _parsed_from_generic
from server.ingest.adapters.cursor import parse_transcript_file
from server.ingest.map import ParsedSession
from server.ingest.project_paths import discover_cursor_transcripts


class CursorAdapter(FileAdapterBase):
    adapter_id = "cursor"
    legacy_source = "cursor"

    def _discover(self) -> list[Path]:
        return [path for path, _parent in discover_cursor_transcripts(self.workspace_root)]

    def parse_path(self, path: Path) -> ParsedSession | None:
        parsed = parse_transcript_file(path, repo_root=self.workspace_root)
        if parsed is None:
            return None
        events = list(parsed.events)
        for link in parsed.sub_agent_links:
            events.append(
                {
                    "type": "sub_agent",
                    "parent_tool_use_id": link["parent_tool_use_id"],
                    "child_session_id": link["child_session_id"],
                    "child_source": link["child_source"],
                }
            )
        status = "best-of-n-subagent" if parsed.is_best_of_n_subcomposer else "completed"
        return _parsed_from_generic(
            source=self.legacy_source,
            external_id=parsed.external_id,
            cwd=parsed.cwd,
            git_branch=None,
            started_at=parsed.started_at,
            ended_at=parsed.ended_at,
            model=parsed.model or "cursor",
            events=events,
            tool_calls=list(parsed.tool_calls),
            usage=parsed.usage.usage,
            has_cost=parsed.has_cost,
            status=status,
        )
