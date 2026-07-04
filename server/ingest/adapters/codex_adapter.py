"""Codex adapter."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.base import FileAdapterBase, _wrap_parse
from server.ingest.adapters.codex import parse_rollout_file
from server.ingest.map import ParsedSession
from server.ingest.project_paths import discover_codex_rollouts


class CodexAdapter(FileAdapterBase):
    adapter_id = "codex"
    legacy_source = "codex"

    def _discover(self) -> list[Path]:
        return discover_codex_rollouts(self.workspace_root)

    def parse_path(self, path: Path) -> ParsedSession | None:
        parsed = parse_rollout_file(path, repo_root=self.workspace_root)
        return _wrap_parse(self.legacy_source, parsed)
