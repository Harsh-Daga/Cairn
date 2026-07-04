"""Outcome and diagnostic domain models (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from server.models._row import (
    dump_json,
    parse_str_list,
    row_bool_int,
    row_float,
    row_int,
    row_required_text,
    row_text,
)


class Outcome(BaseModel):
    """Post-hoc success metrics for a trace."""

    model_config = ConfigDict(frozen=True)

    trace_id: str
    commit_sha: str | None = None
    commit_landed: bool = False
    files_changed: list[str] | None = None
    tests_run: int | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    build_status: str | None = None
    quality_score: float | None = None
    cost_per_success: float | None = None
    outcome_label: str | None = None
    label_source: str | None = None
    captured_at: str | None = None

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "trace_id",
        "commit_sha",
        "commit_landed",
        "files_changed_json",
        "tests_run",
        "tests_passed",
        "tests_failed",
        "build_status",
        "quality_score",
        "cost_per_success",
        "outcome_label",
        "label_source",
        "captured_at",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Outcome:
        files_raw = row["files_changed_json"]
        files_changed = parse_str_list(files_raw) if files_raw is not None else None
        return cls(
            trace_id=row_required_text(row, "trace_id"),
            commit_sha=row_text(row, "commit_sha"),
            commit_landed=row_bool_int(row, "commit_landed"),
            files_changed=files_changed,
            tests_run=row_int(row, "tests_run"),
            tests_passed=row_int(row, "tests_passed"),
            tests_failed=row_int(row, "tests_failed"),
            build_status=row_text(row, "build_status"),
            quality_score=row_float(row, "quality_score"),
            cost_per_success=row_float(row, "cost_per_success"),
            outcome_label=row_text(row, "outcome_label"),
            label_source=row_text(row, "label_source"),
            captured_at=row_text(row, "captured_at"),
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.trace_id,
            self.commit_sha,
            int(self.commit_landed),
            dump_json(self.files_changed),
            self.tests_run,
            self.tests_passed,
            self.tests_failed,
            self.build_status,
            self.quality_score,
            self.cost_per_success,
            self.outcome_label,
            self.label_source,
            self.captured_at,
        )


class Diagnostic(BaseModel):
    """Failure localization summary for a trace."""

    model_config = ConfigDict(frozen=True)

    trace_id: str
    failure_origin_span_id: str | None = None
    failure_signature: str | None = None
    primary_category: str | None = None
    secondary_category: str | None = None
    cascade_root_span_id: str | None = None
    cascade_blast_tokens: int | None = None
    ideal_path_savings_tokens: int | None = None
    computed_at: str | None = None

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "trace_id",
        "failure_origin_span_id",
        "failure_signature",
        "primary_category",
        "secondary_category",
        "cascade_root_span_id",
        "cascade_blast_tokens",
        "ideal_path_savings_tokens",
        "computed_at",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Diagnostic:
        return cls(
            trace_id=row_required_text(row, "trace_id"),
            failure_origin_span_id=row_text(row, "failure_origin_span_id"),
            failure_signature=row_text(row, "failure_signature"),
            primary_category=row_text(row, "primary_category"),
            secondary_category=row_text(row, "secondary_category"),
            cascade_root_span_id=row_text(row, "cascade_root_span_id"),
            cascade_blast_tokens=row_int(row, "cascade_blast_tokens"),
            ideal_path_savings_tokens=row_int(row, "ideal_path_savings_tokens"),
            computed_at=row_text(row, "computed_at"),
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.trace_id,
            self.failure_origin_span_id,
            self.failure_signature,
            self.primary_category,
            self.secondary_category,
            self.cascade_root_span_id,
            self.cascade_blast_tokens,
            self.ideal_path_savings_tokens,
            self.computed_at,
        )
