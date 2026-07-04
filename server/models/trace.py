"""Trace domain model (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from server.models._row import row_float, row_int, row_required_text, row_text


class Trace(BaseModel):
    """Agent session trace with denormalized rollups."""

    model_config = ConfigDict(frozen=True)

    trace_id: str
    workspace_id: str
    source: str
    external_id: str | None = None
    actor_id: str | None = None
    project: str | None = None
    cwd: str | None = None
    model: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    status: str = "completed"
    title: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0
    cost_source: str = "absent"
    context_window: int | None = None
    peak_context_pct: float | None = None
    span_count: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    waste_tokens: int = 0
    difficulty: float | None = None
    difficulty_bucket: str | None = None

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "trace_id",
        "workspace_id",
        "source",
        "external_id",
        "actor_id",
        "project",
        "cwd",
        "model",
        "git_branch",
        "git_commit",
        "started_at",
        "ended_at",
        "status",
        "title",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "reasoning_tokens",
        "cost",
        "cost_source",
        "context_window",
        "peak_context_pct",
        "span_count",
        "tool_calls",
        "tool_errors",
        "waste_tokens",
        "difficulty",
        "difficulty_bucket",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Trace:
        return cls(
            trace_id=row_required_text(row, "trace_id"),
            workspace_id=row_required_text(row, "workspace_id"),
            source=row_required_text(row, "source"),
            external_id=row_text(row, "external_id"),
            actor_id=row_text(row, "actor_id"),
            project=row_text(row, "project"),
            cwd=row_text(row, "cwd"),
            model=row_text(row, "model"),
            git_branch=row_text(row, "git_branch"),
            git_commit=row_text(row, "git_commit"),
            started_at=row_text(row, "started_at"),
            ended_at=row_text(row, "ended_at"),
            status=row_required_text(row, "status"),
            title=row_text(row, "title"),
            input_tokens=row_int(row, "input_tokens", default=0) or 0,
            output_tokens=row_int(row, "output_tokens", default=0) or 0,
            cache_read_tokens=row_int(row, "cache_read_tokens", default=0) or 0,
            cache_creation_tokens=row_int(row, "cache_creation_tokens", default=0) or 0,
            reasoning_tokens=row_int(row, "reasoning_tokens", default=0) or 0,
            cost=row_float(row, "cost") or 0.0,
            cost_source=row_required_text(row, "cost_source"),
            context_window=row_int(row, "context_window"),
            peak_context_pct=row_float(row, "peak_context_pct"),
            span_count=row_int(row, "span_count", default=0) or 0,
            tool_calls=row_int(row, "tool_calls", default=0) or 0,
            tool_errors=row_int(row, "tool_errors", default=0) or 0,
            waste_tokens=row_int(row, "waste_tokens", default=0) or 0,
            difficulty=row_float(row, "difficulty"),
            difficulty_bucket=row_text(row, "difficulty_bucket"),
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.trace_id,
            self.workspace_id,
            self.source,
            self.external_id,
            self.actor_id,
            self.project,
            self.cwd,
            self.model,
            self.git_branch,
            self.git_commit,
            self.started_at,
            self.ended_at,
            self.status,
            self.title,
            self.input_tokens,
            self.output_tokens,
            self.cache_read_tokens,
            self.cache_creation_tokens,
            self.reasoning_tokens,
            self.cost,
            self.cost_source,
            self.context_window,
            self.peak_context_pct,
            self.span_count,
            self.tool_calls,
            self.tool_errors,
            self.waste_tokens,
            self.difficulty,
            self.difficulty_bucket,
        )
