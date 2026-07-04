"""Experiment domain model (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from server.models._row import row_bool_int, row_float, row_int, row_required_text, row_text

ExperimentStatus = Literal[
    "proposed",
    "applied",
    "measuring",
    "verdict",
    "reverted",
    "rejected",
]


class Experiment(BaseModel):
    """Measured improvement experiment loop entry."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    created_at: str
    target_file: str
    block_key: str
    kind: str
    content: str
    evidence_id: str
    status: ExperimentStatus = "proposed"
    applied_at: str | None = None
    min_holdout: int = 8
    baseline_metric: float | None = None
    baseline_n_effective: float | None = None
    outcome_metric: float | None = None
    outcome_n_effective: float | None = None
    effect_estimate: float | None = None
    effect_ci_low: float | None = None
    effect_ci_high: float | None = None
    test_method: str | None = None
    verdict: str | None = None
    confound_flag: bool = False
    measured_at: str | None = None

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "experiment_id",
        "created_at",
        "target_file",
        "block_key",
        "kind",
        "content",
        "evidence_id",
        "status",
        "applied_at",
        "min_holdout",
        "baseline_metric",
        "baseline_n_effective",
        "outcome_metric",
        "outcome_n_effective",
        "effect_estimate",
        "effect_ci_low",
        "effect_ci_high",
        "test_method",
        "verdict",
        "confound_flag",
        "measured_at",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Experiment:
        return cls(
            experiment_id=row_required_text(row, "experiment_id"),
            created_at=row_required_text(row, "created_at"),
            target_file=row_required_text(row, "target_file"),
            block_key=row_required_text(row, "block_key"),
            kind=row_required_text(row, "kind"),
            content=row_required_text(row, "content"),
            evidence_id=row_required_text(row, "evidence_id"),
            status=row_required_text(row, "status"),  # type: ignore[arg-type]
            applied_at=row_text(row, "applied_at"),
            min_holdout=row_int(row, "min_holdout", default=8) or 8,
            baseline_metric=row_float(row, "baseline_metric"),
            baseline_n_effective=row_float(row, "baseline_n_effective"),
            outcome_metric=row_float(row, "outcome_metric"),
            outcome_n_effective=row_float(row, "outcome_n_effective"),
            effect_estimate=row_float(row, "effect_estimate"),
            effect_ci_low=row_float(row, "effect_ci_low"),
            effect_ci_high=row_float(row, "effect_ci_high"),
            test_method=row_text(row, "test_method"),
            verdict=row_text(row, "verdict"),
            confound_flag=row_bool_int(row, "confound_flag"),
            measured_at=row_text(row, "measured_at"),
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.experiment_id,
            self.created_at,
            self.target_file,
            self.block_key,
            self.kind,
            self.content,
            self.evidence_id,
            self.status,
            self.applied_at,
            self.min_holdout,
            self.baseline_metric,
            self.baseline_n_effective,
            self.outcome_metric,
            self.outcome_n_effective,
            self.effect_estimate,
            self.effect_ci_low,
            self.effect_ci_high,
            self.test_method,
            self.verdict,
            int(self.confound_flag),
            self.measured_at,
        )
