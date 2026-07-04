"""Goose session JSONL parser."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.agent_jsonl import parse_agent_jsonl
from server.ingest.types import ParsedAgentSession


def parse_goose_jsonl(
    path: Path,
    *,
    repo_root: Path | None = None,
) -> ParsedAgentSession | None:
    return parse_agent_jsonl(path, source="goose", repo_root=repo_root)
