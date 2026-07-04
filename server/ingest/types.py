"""Shared ingest types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from server.ingest.adapters.claude_code import FileArtifactDraft, ToolCallDraft
from server.ingest.usage import UsageAccumulator

AgentSourceId = Literal[
    "claude-code",
    "codex",
    "cursor",
    "hermes",
    "aider",
    "opencode",
    "goose",
]


@dataclass
class ParsedAgentSession:
    """Normalized parser output consumed by CaptureWriter."""

    source: AgentSourceId
    external_id: str
    cwd: str | None
    git_branch: str | None
    started_at: str | None
    ended_at: str | None
    model: str | None
    events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallDraft] = field(default_factory=list)
    file_artifacts: list[FileArtifactDraft] = field(default_factory=list)
    usage: UsageAccumulator = field(default_factory=UsageAccumulator)
