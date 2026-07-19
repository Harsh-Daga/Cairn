"""Generic JSONL adapters (aider, goose, opencode)."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.aider import parse_aider_jsonl
from server.ingest.adapters.base import FileAdapterBase, _wrap_parse
from server.ingest.adapters.goose import parse_goose_jsonl
from server.ingest.adapters.opencode import parse_opencode_jsonl
from server.ingest.adapters.opencode_db import (
    discover_opencode_db_sessions,
    parse_opencode_session_stub,
)
from server.ingest.map import ParsedSession
from server.ingest.project_paths import (
    discover_aider_sessions,
    discover_goose_sessions,
    discover_opencode_sessions,
)


class AiderAdapter(FileAdapterBase):
    adapter_id = "aider"
    legacy_source = "aider"

    def _discover(self) -> list[Path]:
        return discover_aider_sessions(self.workspace_root)

    def parse_path(self, path: Path) -> ParsedSession | None:
        parsed = parse_aider_jsonl(path, repo_root=self.workspace_root)
        return _wrap_parse(self.legacy_source, parsed)


class GooseAdapter(FileAdapterBase):
    adapter_id = "goose"
    legacy_source = "goose"

    def _discover(self) -> list[Path]:
        return discover_goose_sessions(self.workspace_root)

    def parse_path(self, path: Path) -> ParsedSession | None:
        parsed = parse_goose_jsonl(path, repo_root=self.workspace_root)
        return _wrap_parse(self.legacy_source, parsed)


class OpenCodeAdapter(FileAdapterBase):
    adapter_id = "opencode"
    legacy_source = "opencode"

    def _discover(self) -> list[Path]:
        # Prefer the live SQLite store; keep JSONL sessions as a fallback.
        db_paths = discover_opencode_db_sessions(self.workspace_root)
        jsonl_paths = discover_opencode_sessions(self.workspace_root)
        seen = {path.resolve() for path in db_paths}
        merged = list(db_paths)
        for path in jsonl_paths:
            resolved = path.resolve()
            if resolved not in seen:
                merged.append(resolved)
        return merged

    def parse_path(self, path: Path) -> ParsedSession | None:
        if path.suffix == ".opencode-session" or path.name.endswith(".opencode-session"):
            parsed = parse_opencode_session_stub(path, repo_root=self.workspace_root)
            return _wrap_parse(self.legacy_source, parsed)
        parsed = parse_opencode_jsonl(path, repo_root=self.workspace_root)
        return _wrap_parse(self.legacy_source, parsed)
