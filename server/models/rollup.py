"""Daily rollup domain model (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from server.models._row import row_float, row_int, row_required_text, row_text


class RollupDaily(BaseModel):
    """Aggregated daily usage metrics by workspace/project/source/model."""

    model_config = ConfigDict(frozen=True)

    day: str
    workspace_id: str
    project: str
    source: str
    model: str = ""
    traces: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost: float = 0.0
    waste_tokens: int = 0

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "day",
        "workspace_id",
        "project",
        "source",
        "model",
        "traces",
        "tool_calls",
        "tool_errors",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
        "cost",
        "waste_tokens",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> RollupDaily:
        return cls(
            day=row_required_text(row, "day"),
            workspace_id=row_required_text(row, "workspace_id"),
            project=row_required_text(row, "project"),
            source=row_required_text(row, "source"),
            model=row_text(row, "model") or "",
            traces=row_int(row, "traces", default=0) or 0,
            tool_calls=row_int(row, "tool_calls", default=0) or 0,
            tool_errors=row_int(row, "tool_errors", default=0) or 0,
            input_tokens=row_int(row, "input_tokens", default=0) or 0,
            output_tokens=row_int(row, "output_tokens", default=0) or 0,
            cache_read_tokens=row_int(row, "cache_read_tokens", default=0) or 0,
            cache_creation_tokens=row_int(row, "cache_creation_tokens", default=0) or 0,
            cost=row_float(row, "cost") or 0.0,
            waste_tokens=row_int(row, "waste_tokens", default=0) or 0,
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.day,
            self.workspace_id,
            self.project,
            self.source,
            self.model,
            self.traces,
            self.tool_calls,
            self.tool_errors,
            self.input_tokens,
            self.output_tokens,
            self.cache_read_tokens,
            self.cache_creation_tokens,
            self.cost,
            self.waste_tokens,
        )
