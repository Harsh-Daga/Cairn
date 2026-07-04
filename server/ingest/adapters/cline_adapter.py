"""Cline / Roo / Kilo adapters."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.base import FileAdapterBase, _wrap_parse
from server.ingest.adapters.cline_family import discover_cline_sessions, parse_cline_task
from server.ingest.map import ParsedSession


class _ClineFamilyAdapter(FileAdapterBase):
    legacy_source: str

    def _discover(self) -> list[Path]:
        pairs = discover_cline_sessions(self.workspace_root)
        return [path for path, source in pairs if source == self.legacy_source]

    def parse_path(self, path: Path) -> ParsedSession | None:
        return _wrap_parse(
            self.legacy_source,
            parse_cline_task(path, source=self.legacy_source, repo_root=self.workspace_root),
        )


class ClineAdapter(_ClineFamilyAdapter):
    adapter_id = "cline"
    legacy_source = "cline"


class RooAdapter(_ClineFamilyAdapter):
    adapter_id = "roo"
    legacy_source = "roo"


class KiloAdapter(_ClineFamilyAdapter):
    adapter_id = "kilo"
    legacy_source = "kilo"
