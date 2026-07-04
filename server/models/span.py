"""Span domain model (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.models._row import (
    dump_json,
    parse_json_dict,
    row_int,
    row_required_text,
    row_text,
)

SpanKind = Literal[
    "agent",
    "llm_call",
    "tool_call",
    "tool_result",
    "user_msg",
    "assistant_msg",
    "retrieval",
    "subagent",
    "compaction",
    "system",
]
SpanStatus = Literal["ok", "error", "cancelled"]


class Span(BaseModel):
    """Ordered span within a trace (causality tree node)."""

    model_config = ConfigDict(frozen=True)

    span_id: str
    trace_id: str
    parent_span_id: str | None = None
    seq: int
    kind: SpanKind
    name: str | None = None
    agent_id: str | None = None
    agent_lane: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    status: SpanStatus = "ok"
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    input_estimated: int = 0
    output_estimated: int = 0
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    context_tokens_after: int | None = None
    text_inline: str | None = None
    text_hash: str | None = None
    args_hash: str | None = None
    path_rel: str | None = None
    waste_category: str | None = None
    waste_tokens: int = 0
    attrs_json: dict[str, object] = Field(default_factory=dict)

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "span_id",
        "trace_id",
        "parent_span_id",
        "seq",
        "kind",
        "name",
        "agent_id",
        "agent_lane",
        "started_at",
        "ended_at",
        "duration_ms",
        "status",
        "model",
        "input_tokens",
        "output_tokens",
        "input_estimated",
        "output_estimated",
        "cache_read_tokens",
        "cache_creation_tokens",
        "context_tokens_after",
        "text_inline",
        "text_hash",
        "args_hash",
        "path_rel",
        "waste_category",
        "waste_tokens",
        "attrs_json",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Span:
        return cls(
            span_id=row_required_text(row, "span_id"),
            trace_id=row_required_text(row, "trace_id"),
            parent_span_id=row_text(row, "parent_span_id"),
            seq=int(row["seq"]),
            kind=row_required_text(row, "kind"),  # type: ignore[arg-type]
            name=row_text(row, "name"),
            agent_id=row_text(row, "agent_id"),
            agent_lane=row_text(row, "agent_lane"),
            started_at=row_text(row, "started_at"),
            ended_at=row_text(row, "ended_at"),
            duration_ms=row_int(row, "duration_ms"),
            status=row_required_text(row, "status"),  # type: ignore[arg-type]
            model=row_text(row, "model"),
            input_tokens=row_int(row, "input_tokens"),
            output_tokens=row_int(row, "output_tokens"),
            input_estimated=row_int(row, "input_estimated", default=0) or 0,
            output_estimated=row_int(row, "output_estimated", default=0) or 0,
            cache_read_tokens=row_int(row, "cache_read_tokens"),
            cache_creation_tokens=row_int(row, "cache_creation_tokens"),
            context_tokens_after=row_int(row, "context_tokens_after"),
            text_inline=row_text(row, "text_inline"),
            text_hash=row_text(row, "text_hash"),
            args_hash=row_text(row, "args_hash"),
            path_rel=row_text(row, "path_rel"),
            waste_category=row_text(row, "waste_category"),
            waste_tokens=row_int(row, "waste_tokens", default=0) or 0,
            attrs_json=parse_json_dict(row["attrs_json"]),
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.span_id,
            self.trace_id,
            self.parent_span_id,
            self.seq,
            self.kind,
            self.name,
            self.agent_id,
            self.agent_lane,
            self.started_at,
            self.ended_at,
            self.duration_ms,
            self.status,
            self.model,
            self.input_tokens,
            self.output_tokens,
            self.input_estimated,
            self.output_estimated,
            self.cache_read_tokens,
            self.cache_creation_tokens,
            self.context_tokens_after,
            self.text_inline,
            self.text_hash,
            self.args_hash,
            self.path_rel,
            self.waste_category,
            self.waste_tokens,
            dump_json(self.attrs_json),
        )
