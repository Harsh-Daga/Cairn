"""Context region domain model (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from server.models._row import row_bool_int, row_float, row_int, row_required_text, row_text

ContextRegionName = Literal[
    "system",
    "tool_schema",
    "tool_result",
    "retrieved",
    "user",
    "history",
]


class ContextRegion(BaseModel):
    """Token/cost breakdown for a span context region."""

    model_config = ConfigDict(frozen=True)

    span_id: str
    region: ContextRegionName
    tokens: int = 0
    cost: float = 0.0
    content_hash: str | None = None
    first_turn: int | None = None
    last_seen_turn: int | None = None
    still_in_window: bool = False

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "span_id",
        "region",
        "tokens",
        "cost",
        "content_hash",
        "first_turn",
        "last_seen_turn",
        "still_in_window",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ContextRegion:
        return cls(
            span_id=row_required_text(row, "span_id"),
            region=row_required_text(row, "region"),  # type: ignore[arg-type]
            tokens=row_int(row, "tokens", default=0) or 0,
            cost=row_float(row, "cost") or 0.0,
            content_hash=row_text(row, "content_hash"),
            first_turn=row_int(row, "first_turn"),
            last_seen_turn=row_int(row, "last_seen_turn"),
            still_in_window=row_bool_int(row, "still_in_window"),
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.span_id,
            self.region,
            self.tokens,
            self.cost,
            self.content_hash,
            self.first_turn,
            self.last_seen_turn,
            int(self.still_in_window),
        )
