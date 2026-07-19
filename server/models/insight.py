"""Insight domain models (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from server.models._row import (
    dump_json,
    parse_json_dict,
    row_float,
    row_int,
    row_required_text,
    row_text,
)

InsightSeverity = Literal["info", "suggestion", "warning", "error"]
InsightLifecycle = Literal["new", "ack", "fixed", "regressed", "muted"]


class Insight(BaseModel):
    """Detector-produced insight with dedupe fingerprint."""

    model_config = ConfigDict(frozen=True)

    insight_id: str
    fingerprint: str
    detector: str
    detector_version: int
    severity: InsightSeverity
    title: str
    body: str
    evidence_id: str
    savings_estimate: float | None = None
    savings_ci: dict[str, object] | None = None
    action: str | None = None
    created_at: str
    last_seen_at: str

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "insight_id",
        "fingerprint",
        "detector",
        "detector_version",
        "severity",
        "title",
        "body",
        "evidence_id",
        "savings_estimate",
        "savings_ci_json",
        "action",
        "created_at",
        "last_seen_at",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Insight:
        ci_raw = row["savings_ci_json"]
        savings_ci = parse_json_dict(ci_raw) if ci_raw is not None else None
        return cls(
            insight_id=row_required_text(row, "insight_id"),
            fingerprint=row_required_text(row, "fingerprint"),
            detector=row_required_text(row, "detector"),
            detector_version=int(row["detector_version"]),
            severity=row_required_text(row, "severity"),  # type: ignore[arg-type]
            title=row_required_text(row, "title"),
            body=row_required_text(row, "body"),
            evidence_id=row_required_text(row, "evidence_id"),
            savings_estimate=row_float(row, "savings_estimate"),
            savings_ci=savings_ci,
            action=row_text(row, "action"),
            created_at=row_required_text(row, "created_at"),
            last_seen_at=row_required_text(row, "last_seen_at"),
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.insight_id,
            self.fingerprint,
            self.detector,
            self.detector_version,
            self.severity,
            self.title,
            self.body,
            self.evidence_id,
            self.savings_estimate,
            dump_json(self.savings_ci),
            self.action,
            self.created_at,
            self.last_seen_at,
        )


class InsightState(BaseModel):
    """User lifecycle state for an insight."""

    model_config = ConfigDict(frozen=True)

    insight_id: str
    state: InsightLifecycle = "new"
    changed_at: str
    changed_by: str | None = None
    snoozed_until: str | None = None
    snooze_savings_baseline: float | None = None
    see_count: int = 1

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "insight_id",
        "state",
        "changed_at",
        "changed_by",
        "snoozed_until",
        "snooze_savings_baseline",
        "see_count",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> InsightState:
        keys = set(row.keys())
        return cls(
            insight_id=row_required_text(row, "insight_id"),
            state=row_required_text(row, "state"),  # type: ignore[arg-type]
            changed_at=row_required_text(row, "changed_at"),
            changed_by=row_text(row, "changed_by"),
            snoozed_until=row_text(row, "snoozed_until") if "snoozed_until" in keys else None,
            snooze_savings_baseline=(
                row_float(row, "snooze_savings_baseline")
                if "snooze_savings_baseline" in keys
                else None
            ),
            see_count=(
                int(row_int(row, "see_count", default=1) or 1) if "see_count" in keys else 1
            ),
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.insight_id,
            self.state,
            self.changed_at,
            self.changed_by,
            self.snoozed_until,
            self.snooze_savings_baseline,
            self.see_count,
        )
