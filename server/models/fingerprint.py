"""Fingerprint domain models (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from server.models._row import (
    dump_json,
    parse_float_list,
    parse_json,
    row_float,
    row_int,
    row_required_text,
    row_text,
)


class Fingerprint(BaseModel):
    """Behavioral fingerprint vector for a trace."""

    model_config = ConfigDict(frozen=True)

    trace_id: str
    project: str | None = None
    model: str | None = None
    source: str | None = None
    week: str | None = None
    ts: str | None = None
    vector: list[float] = Field(default_factory=list)
    read_write_ratio: float | None = None
    exploration_ratio: float | None = None
    retry_rate: float | None = None
    tool_entropy: float | None = None
    turn_count: int | None = None
    context_fill_traj: list[float] | None = None

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "trace_id",
        "project",
        "model",
        "source",
        "week",
        "ts",
        "vector_json",
        "read_write_ratio",
        "exploration_ratio",
        "retry_rate",
        "tool_entropy",
        "turn_count",
        "context_fill_traj_json",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Fingerprint:
        traj_raw = row["context_fill_traj_json"]
        context_fill_traj = (
            parse_float_list(traj_raw) if traj_raw is not None else None
        )
        return cls(
            trace_id=row_required_text(row, "trace_id"),
            project=row_text(row, "project"),
            model=row_text(row, "model"),
            source=row_text(row, "source"),
            week=row_text(row, "week"),
            ts=row_text(row, "ts"),
            vector=parse_float_list(row["vector_json"]),
            read_write_ratio=row_float(row, "read_write_ratio"),
            exploration_ratio=row_float(row, "exploration_ratio"),
            retry_rate=row_float(row, "retry_rate"),
            tool_entropy=row_float(row, "tool_entropy"),
            turn_count=row_int(row, "turn_count"),
            context_fill_traj=context_fill_traj,
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.trace_id,
            self.project,
            self.model,
            self.source,
            self.week,
            self.ts,
            dump_json(self.vector),
            self.read_write_ratio,
            self.exploration_ratio,
            self.retry_rate,
            self.tool_entropy,
            self.turn_count,
            dump_json(self.context_fill_traj),
        )


class FingerprintBaseline(BaseModel):
    """Rolling baseline for fingerprint Mahalanobis distance."""

    model_config = ConfigDict(frozen=True)

    project: str
    model: str
    week: str
    mean_vector: list[float] = Field(default_factory=list)
    cov_inv: list[list[float]] = Field(default_factory=list)
    n: int

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "project",
        "model",
        "week",
        "mean_vector_json",
        "cov_inv_json",
        "n",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> FingerprintBaseline:
        cov_raw = parse_json(row["cov_inv_json"])
        cov_inv: list[list[float]] = []
        if isinstance(cov_raw, list):
            for row_item in cov_raw:
                if isinstance(row_item, list):
                    cov_inv.append([float(v) for v in row_item])
        return cls(
            project=row_required_text(row, "project"),
            model=row_required_text(row, "model"),
            week=row_required_text(row, "week"),
            mean_vector=parse_float_list(row["mean_vector_json"]),
            cov_inv=cov_inv,
            n=int(row["n"]),
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.project,
            self.model,
            self.week,
            dump_json(self.mean_vector),
            dump_json(self.cov_inv),
            self.n,
        )
