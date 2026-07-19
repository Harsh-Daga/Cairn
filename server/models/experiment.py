"""Experiment domain model (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.models._row import (
    dump_json,
    parse_float_list,
    parse_json_list,
    parse_str_list,
    row_bool_int,
    row_float,
    row_int,
    row_required_text,
    row_text,
)

ExperimentStatus = Literal[
    "proposed",
    "applied",
    "measuring",
    "verdict",
    "reverted",
    "rejected",
]
DecayState = Literal["healthy", "decaying", "decayed", "unknown"]
ProposalSource = Literal["local", "provider"]


class VerdictHistoryEntry(BaseModel):
    """Immutable snapshot of a prior measured verdict."""

    model_config = ConfigDict(frozen=True)

    at: str
    verdict: str | None = None
    plain_verdict: str | None = None
    effect_estimate: float | None = None
    effect_ci_low: float | None = None
    effect_ci_high: float | None = None
    sample_size: float | None = None
    outcome_n_raw: int | None = None
    decay_state: DecayState | None = None
    regression_outside_interval: bool = False


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
    baseline_n_raw: int | None = None
    outcome_metric: float | None = None
    outcome_n_effective: float | None = None
    outcome_n_raw: int | None = None
    effect_estimate: float | None = None
    effect_ci_low: float | None = None
    effect_ci_high: float | None = None
    test_method: str | None = None
    verdict: str | None = None
    confound_flag: bool = False
    measured_at: str | None = None
    agent_type: str | None = None
    proposal_source: ProposalSource = "local"
    decay_state: DecayState = "unknown"
    last_evaluated_at: str | None = None
    plain_verdict: str | None = None
    confound_notes: list[str] = Field(default_factory=list)
    effect_history: list[float] = Field(default_factory=list)
    guard_event_id: str | None = None
    eval_interval_days: int = 30
    verdict_history: list[VerdictHistoryEntry] = Field(default_factory=list)
    regression_outside_interval: bool = False

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
        "baseline_n_raw",
        "outcome_metric",
        "outcome_n_effective",
        "outcome_n_raw",
        "effect_estimate",
        "effect_ci_low",
        "effect_ci_high",
        "test_method",
        "verdict",
        "confound_flag",
        "measured_at",
        "agent_type",
        "proposal_source",
        "decay_state",
        "last_evaluated_at",
        "plain_verdict",
        "confound_notes_json",
        "effect_history_json",
        "guard_event_id",
        "eval_interval_days",
        "verdict_history_json",
        "regression_outside_interval",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Experiment:
        keys = set(row.keys())
        notes_raw = row["confound_notes_json"] if "confound_notes_json" in keys else None
        history_raw = row["effect_history_json"] if "effect_history_json" in keys else None
        verdict_hist_raw = row["verdict_history_json"] if "verdict_history_json" in keys else None
        confound_notes = parse_str_list(notes_raw) if notes_raw is not None else []
        effect_history = parse_float_list(history_raw) if history_raw is not None else []
        verdict_history: list[VerdictHistoryEntry] = []
        if verdict_hist_raw is not None:
            for item in parse_json_list(verdict_hist_raw):
                if isinstance(item, dict):
                    verdict_history.append(VerdictHistoryEntry.model_validate(item))
        source = row_text(row, "proposal_source") if "proposal_source" in keys else "local"
        if source not in {"local", "provider"}:
            source = "local"
        decay = row_text(row, "decay_state") if "decay_state" in keys else "unknown"
        if decay not in {"healthy", "decaying", "decayed", "unknown"}:
            decay = "unknown"
        interval = (
            row_int(row, "eval_interval_days", default=30) if "eval_interval_days" in keys else 30
        ) or 30
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
            baseline_n_raw=row_int(row, "baseline_n_raw"),
            outcome_metric=row_float(row, "outcome_metric"),
            outcome_n_effective=row_float(row, "outcome_n_effective"),
            outcome_n_raw=row_int(row, "outcome_n_raw"),
            effect_estimate=row_float(row, "effect_estimate"),
            effect_ci_low=row_float(row, "effect_ci_low"),
            effect_ci_high=row_float(row, "effect_ci_high"),
            test_method=row_text(row, "test_method"),
            verdict=row_text(row, "verdict"),
            confound_flag=row_bool_int(row, "confound_flag"),
            measured_at=row_text(row, "measured_at"),
            agent_type=row_text(row, "agent_type"),
            proposal_source=source,  # type: ignore[arg-type]
            decay_state=decay,  # type: ignore[arg-type]
            last_evaluated_at=(
                row_text(row, "last_evaluated_at") if "last_evaluated_at" in keys else None
            ),
            plain_verdict=row_text(row, "plain_verdict") if "plain_verdict" in keys else None,
            confound_notes=confound_notes,
            effect_history=effect_history,
            guard_event_id=row_text(row, "guard_event_id") if "guard_event_id" in keys else None,
            eval_interval_days=interval,
            verdict_history=verdict_history,
            regression_outside_interval=(
                row_bool_int(row, "regression_outside_interval")
                if "regression_outside_interval" in keys
                else False
            ),
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
            self.baseline_n_raw,
            self.outcome_metric,
            self.outcome_n_effective,
            self.outcome_n_raw,
            self.effect_estimate,
            self.effect_ci_low,
            self.effect_ci_high,
            self.test_method,
            self.verdict,
            int(self.confound_flag),
            self.measured_at,
            self.agent_type,
            self.proposal_source,
            self.decay_state,
            self.last_evaluated_at,
            self.plain_verdict,
            dump_json(self.confound_notes) if self.confound_notes else None,
            dump_json(self.effect_history) if self.effect_history else None,
            self.guard_event_id,
            self.eval_interval_days,
            dump_json([entry.model_dump(mode="json") for entry in self.verdict_history])
            if self.verdict_history
            else None,
            int(self.regression_outside_interval),
        )
