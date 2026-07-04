"""Evidence and view-state domain models (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from server.models._row import (
    dump_json,
    parse_json_dict,
    parse_str_list,
    row_required_text,
)


class Evidence(BaseModel):
    """Provenance record for analyzer outputs."""

    model_config = ConfigDict(frozen=True)

    evidence_id: str
    producer: str
    produced_at: str
    trace_ids: list[str] = Field(default_factory=list)
    span_ids: list[str] | None = None
    metrics: dict[str, object] = Field(default_factory=dict)

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "evidence_id",
        "producer",
        "produced_at",
        "trace_ids_json",
        "span_ids_json",
        "metrics_json",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Evidence:
        span_raw = row["span_ids_json"]
        span_ids = parse_str_list(span_raw) if span_raw is not None else None
        return cls(
            evidence_id=row_required_text(row, "evidence_id"),
            producer=row_required_text(row, "producer"),
            produced_at=row_required_text(row, "produced_at"),
            trace_ids=parse_str_list(row["trace_ids_json"]),
            span_ids=span_ids,
            metrics=parse_json_dict(row["metrics_json"]),
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.evidence_id,
            self.producer,
            self.produced_at,
            dump_json(self.trace_ids),
            dump_json(self.span_ids),
            dump_json(self.metrics),
        )


class ViewState(BaseModel):
    """Incremental view maintenance ledger entry."""

    model_config = ConfigDict(frozen=True)

    view: str
    key: str
    version: int
    input_hash: str
    computed_at: str

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "view",
        "key",
        "version",
        "input_hash",
        "computed_at",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ViewState:
        return cls(
            view=row_required_text(row, "view"),
            key=row_required_text(row, "key"),
            version=int(row["version"]),
            input_hash=row_required_text(row, "input_hash"),
            computed_at=row_required_text(row, "computed_at"),
        )

    def to_row(self) -> tuple[str, str, int, str, str]:
        return (self.view, self.key, self.version, self.input_hash, self.computed_at)
