"""Capture session domain types (charter §5, Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

AgentSource = Literal[
    "claude-code",
    "codex",
    "cursor",
    "hermes",
    "aider",
    "openhands",
    "goose",
]

SessionStatus = Literal["in_progress", "completed", "error"]

EventType = Literal[
    "session_start",
    "session_end",
    "user_prompt",
    "assistant_message",
    "tool_call",
    "tool_result",
    "file_snapshot",
    "sub_agent",
    "error",
]

RunKind = Literal["capture", "build", "provider"]


@dataclass(frozen=True)
class SessionEvent:
    """One normalized event in a capture session trajectory."""

    seq: int
    event_type: EventType
    payload: dict[str, Any]
    timestamp: str | None = None


@dataclass(frozen=True)
class Session:
    """A continuous agent conversation or provider-attached session."""

    run_id: str
    external_id: str
    source: AgentSource
    status: SessionStatus
    started_at: str
    ended_at: str | None
    cwd: str | None
    git_branch: str | None
    git_commit: str | None
    model: str | None
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float | None
    trajectory_hash: str | None
    event_count: int

    @property
    def session_key(self) -> str:
        return f"{self.source}:{self.external_id}"

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "external_id": self.external_id,
            "source": self.source,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "cwd": self.cwd,
            "git_branch": self.git_branch,
            "git_commit": self.git_commit,
            "model": self.model,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost": self.total_cost,
            "trajectory_hash": self.trajectory_hash,
            "event_count": self.event_count,
            "session_key": self.session_key,
        }


def session_from_writer_summary(
    summary: SessionSummaryBridge,
) -> Session:
    """Bridge ingest SessionSummary → domain Session."""
    return Session(
        run_id=summary.run_id,
        external_id=summary.external_id,
        source=summary.source,  # type: ignore[arg-type]
        status=summary.status,  # type: ignore[arg-type]
        started_at=summary.started_at,
        ended_at=summary.ended_at,
        cwd=summary.cwd,
        git_branch=summary.git_branch,
        git_commit=summary.git_commit,
        model=summary.model,
        total_input_tokens=summary.total_input_tokens,
        total_output_tokens=summary.total_output_tokens,
        total_cost=summary.total_cost,
        trajectory_hash=summary.trajectory_hash,
        event_count=summary.event_count,
    )


class SessionSummaryBridge(Protocol):
    """Structural typing bridge for ingest SessionSummary without circular imports."""

    run_id: str
    external_id: str
    source: str
    cwd: str | None
    git_branch: str | None
    git_commit: str | None
    started_at: str
    ended_at: str | None
    status: str
    model: str | None
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float | None
    trajectory_hash: str | None
    event_count: int
