"""Hermes adapter."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.base import FileAdapterBase, _wrap_parse
from server.ingest.adapters.hermes import parse_session_file
from server.ingest.map import ParsedSession
from server.ingest.project_paths import discover_hermes_sessions


class HermesAdapter(FileAdapterBase):
    adapter_id = "hermes"
    legacy_source = "hermes"

    def _discover(self) -> list[Path]:
        return discover_hermes_sessions(self.workspace_root)

    def parse_path(self, path: Path) -> ParsedSession | None:
        parsed = parse_session_file(path, repo_root=self.workspace_root)
        return _wrap_parse(self.legacy_source, parsed)
