"""Claude Code adapter."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.base import FileAdapterBase, _wrap_parse
from server.ingest.adapters.claude_code import parse_jsonl_file
from server.ingest.map import ParsedSession
from server.ingest.project_paths import discover_claude_jsonl


class ClaudeCodeAdapter(FileAdapterBase):
    adapter_id = "claude_code"
    legacy_source = "claude-code"

    def _discover(self) -> list[Path]:
        return discover_claude_jsonl(self.workspace_root)

    def parse_path(self, path: Path) -> ParsedSession | None:
        parsed = parse_jsonl_file(path, repo_root=self.workspace_root)
        return _wrap_parse(self.legacy_source, parsed)
