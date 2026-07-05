"""Experiment registry — create, apply, measure, verdict."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from server.improve.apply import ManagedEntry, apply_entries, revert_from_backup
from server.improve.stats import clustered_effective_n, measure_causal_effect
from server.models.experiment import Experiment
from server.store.repos.experiments import ExperimentRepo
from server.util.ids import new_ulid

LOOKBACK_DAYS = 14
MIN_TRACES_PER_WEEK = 5.0


@dataclass(frozen=True)
class MeasureResult:
    experiment_id: str
    verdict: str
    effect_estimate: float | None
    n_effective: float
    gated: bool


@dataclass(frozen=True)
class PreviewResult:
    expected_days_to_verdict: float | None
    traces_per_day: float
    n_effective_needed: float
    traffic_unknown: bool


def preview(
    conn: sqlite3.Connection,
    experiment: Experiment,
    *,
    workspace_id: str,
    lookback_days: int = LOOKBACK_DAYS,
    min_traces_per_week: float = MIN_TRACES_PER_WEEK,
) -> PreviewResult:
    """Estimate days to verdict from trailing session traffic."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM traces
        WHERE workspace_id = ? AND started_at >= date('now', ?)
        """,
        (workspace_id, f"-{lookback_days} days"),
    ).fetchone()
    count = int(row[0]) if row else 0
    traces_per_day = count / lookback_days if lookback_days > 0 else 0.0
    n_effective_needed = float(experiment.min_holdout)
    min_per_day = min_traces_per_week / 7.0
    traffic_unknown = traces_per_day < min_per_day
    expected_days: float | None = None
    if not traffic_unknown and traces_per_day > 0:
        expected_days = n_effective_needed / traces_per_day
    return PreviewResult(
        expected_days_to_verdict=expected_days,
        traces_per_day=round(traces_per_day, 3),
        n_effective_needed=n_effective_needed,
        traffic_unknown=traffic_unknown,
    )


def create_experiment(
    conn: sqlite3.Connection,
    *,
    target_file: str,
    block_key: str,
    kind: str,
    content: str,
    evidence_id: str,
    min_holdout: int = 8,
) -> Experiment:
    now = datetime.now(UTC).isoformat()
    exp = Experiment(
        experiment_id=new_ulid(),
        created_at=now,
        target_file=target_file,
        block_key=block_key,
        kind=kind,
        content=content,
        evidence_id=evidence_id,
        status="proposed",
        min_holdout=min_holdout,
    )
    ExperimentRepo.create(conn, exp)
    return exp


def apply_experiment(
    conn: sqlite3.Connection,
    experiment: Experiment,
    *,
    repo_root: Path,
) -> Experiment:
    target = repo_root / experiment.target_file
    backup_dir = repo_root / ".cairn" / "backups"
    entry = ManagedEntry(
        kind=experiment.kind,
        entry_id=experiment.block_key,
        content=experiment.content,
    )
    apply_entries(target, [entry], backup_dir=backup_dir)
    now = datetime.now(UTC).isoformat()
    updated = experiment.model_copy(update={"status": "applied", "applied_at": now})
    ExperimentRepo.update(conn, updated)
    return updated


def revert_experiment(
    conn: sqlite3.Connection,
    experiment: Experiment,
    *,
    repo_root: Path,
    backup: Path,
) -> Experiment:
    target = repo_root / experiment.target_file
    revert_from_backup(target, backup)
    now = datetime.now(UTC).isoformat()
    updated = experiment.model_copy(update={"status": "reverted", "measured_at": now})
    ExperimentRepo.update(conn, updated)
    return updated


def measure_experiment(
    conn: sqlite3.Connection,
    experiment: Experiment,
    *,
    pre_trace_ids: list[str],
    post_trace_ids: list[str],
    metric_fn: object,
    clusters: list[str] | None = None,
) -> MeasureResult:
    """Gate on min_holdout effective n before emitting verdict."""
    post_values = [metric_fn(tid) for tid in post_trace_ids]  # type: ignore[operator]
    cluster_keys = clusters or [str(i) for i in range(len(post_trace_ids))]
    n_eff = clustered_effective_n(post_values, cluster_keys)
    gated = n_eff < float(experiment.min_holdout)
    if gated:
        return MeasureResult(
            experiment_id=experiment.experiment_id,
            verdict="inconclusive",
            effect_estimate=None,
            n_effective=n_eff,
            gated=True,
        )
    causal = measure_causal_effect(
        conn,
        pre_trace_ids=pre_trace_ids,
        post_trace_ids=post_trace_ids,
        metric_fn=metric_fn,  # type: ignore[arg-type]
    )
    now = datetime.now(UTC).isoformat()
    updated = experiment.model_copy(
        update={
            "status": "verdict",
            "outcome_n_effective": n_eff,
            "effect_estimate": causal.effect_estimate,
            "effect_ci_low": causal.effect_ci_low,
            "effect_ci_high": causal.effect_ci_high,
            "test_method": causal.test_method,
            "verdict": causal.verdict,
            "confound_flag": causal.confound_flag,
            "measured_at": now,
        }
    )
    ExperimentRepo.update(conn, updated)
    return MeasureResult(
        experiment_id=experiment.experiment_id,
        verdict=causal.verdict,
        effect_estimate=causal.effect_estimate,
        n_effective=n_eff,
        gated=False,
    )
