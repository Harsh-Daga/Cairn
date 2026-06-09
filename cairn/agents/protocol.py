"""Agent parser protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from cairn.ingest.types import AgentSourceId, ParsedAgentSession


class AgentParser(Protocol):
    source_id: AgentSourceId

    def parse_file(
        self,
        path: Path,
        *,
        repo_root: Path | None = None,
    ) -> ParsedAgentSession | None: ...
