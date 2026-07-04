"""OpenClaw adapter."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.base import FileAdapterBase, _wrap_parse
from server.ingest.adapters.openclaw import discover_openclaw_sessions, parse_openclaw_file
from server.ingest.map import ParsedSession


class OpenClawAdapter(FileAdapterBase):
    adapter_id = "openclaw"
    legacy_source = "openclaw"

    def _discover(self) -> list[Path]:
        return discover_openclaw_sessions(self.workspace_root)

    def parse_path(self, path: Path) -> ParsedSession | None:
        parsed = parse_openclaw_file(path, repo_root=self.workspace_root)
        return _wrap_parse(self.legacy_source, parsed)
