"""Gemini CLI adapter."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.base import FileAdapterBase, _wrap_parse
from server.ingest.adapters.gemini_cli import discover_gemini_sessions, parse_gemini_file
from server.ingest.map import ParsedSession


class GeminiAdapter(FileAdapterBase):
    adapter_id = "gemini_cli"
    legacy_source = "gemini"

    def _discover(self) -> list[Path]:
        return discover_gemini_sessions(self.workspace_root)

    def parse_path(self, path: Path) -> ParsedSession | None:
        parsed = parse_gemini_file(path, repo_root=self.workspace_root)
        return _wrap_parse(self.legacy_source, parsed)
