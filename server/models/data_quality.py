"""Data quality domain model (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from server.models._row import (
    dump_json,
    parse_json_dict,
    row_bool_int,
    row_float,
    row_int,
    row_required_text,
    row_text,
)


class DataQuality(BaseModel):
    """Ingest/parser quality metrics for a trace."""

    model_config = ConfigDict(frozen=True)

    trace_id: str
    pct_tokens_measured: float | None = None
    pct_tokens_estimated: float | None = None
    timestamps_present: bool = False
    cost_source: str = "absent"
    parser_version: str | None = None
    dropped_events: int = 0
    notes: dict[str, object] = Field(default_factory=dict)
    computed_at: str | None = None

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "trace_id",
        "pct_tokens_measured",
        "pct_tokens_estimated",
        "timestamps_present",
        "cost_source",
        "parser_version",
        "dropped_events",
        "notes_json",
        "computed_at",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> DataQuality:
        notes_raw = row["notes_json"]
        notes = parse_json_dict(notes_raw) if notes_raw is not None else {}
        return cls(
            trace_id=row_required_text(row, "trace_id"),
            pct_tokens_measured=row_float(row, "pct_tokens_measured"),
            pct_tokens_estimated=row_float(row, "pct_tokens_estimated"),
            timestamps_present=row_bool_int(row, "timestamps_present"),
            cost_source=row_required_text(row, "cost_source"),
            parser_version=row_text(row, "parser_version"),
            dropped_events=row_int(row, "dropped_events", default=0) or 0,
            notes=notes,
            computed_at=row_text(row, "computed_at"),
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.trace_id,
            self.pct_tokens_measured,
            self.pct_tokens_estimated,
            int(self.timestamps_present),
            self.cost_source,
            self.parser_version,
            self.dropped_events,
            dump_json(self.notes) if self.notes else None,
            self.computed_at,
        )
