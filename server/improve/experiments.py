"""Experiment registry — create, apply, measure, verdict."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from server.improve.apply import ManagedEntry, apply_entries, revert_from_backup
from server.improve.stats import clustered_effective_n, measure_causal_effect
from server.models.experiment import (
    DecayState,
    Experiment,
    ProposalSource,
    VerdictHistoryEntry,
)
from server.store.repos.experiments import ExperimentRepo
from server.util.ids import new_ulid

LOOKBACK_DAYS = 14
MIN_TRACES_PER_WEEK = 5.0
DECAY_DAYS = 30
PORTFOLIO_REEVAL_STATUSES = frozenset({"applied", "measuring", "verdict"})
MAX_VERDICT_HISTORY = 24


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
    proposal_source: ProposalSource = "local",
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
        proposal_source=proposal_source,
        decay_state="unknown",
    )
    ExperimentRepo.create(conn, exp)
    return exp


def plain_verdict_text(
    *,
    verdict: str | None,
    effect_estimate: float | None,
    confound_flag: bool,
    confound_notes: list[str],
) -> str:
    if confound_flag or verdict == "confounded":
        reason = "; ".join(confound_notes[:2]) if confound_notes else "mix shifted between windows"
        return f"No causal claim: measurement is confounded ({reason})."
    if verdict == "improved":
        pct = f"{(effect_estimate or 0.0) * 100:.0f}%" if effect_estimate is not None else "an"
        return f"Holdout evidence suggests this rule improved the metric by about {pct}."
    if verdict == "regressed":
        pct = f"{abs(effect_estimate or 0.0) * 100:.0f}%" if effect_estimate is not None else "an"
        return f"Holdout evidence suggests this rule worsened the metric by about {pct}."
    if verdict == "no_effect":
        return "Holdout evidence is consistent with no practical effect from this rule."
    if verdict == "inconclusive":
        return "Not enough holdout evidence yet for a verdict."
    return "No measured verdict yet."


def evaluate_decay(experiment: Experiment, *, now: datetime | None = None) -> DecayState:
    """Descriptive decay label from verdict age, confound state, and interval drift."""
    current = now or datetime.now(UTC)
    if experiment.status in {"proposed", "applied", "measuring"}:
        return "unknown"
    if experiment.status == "reverted":
        return "decayed"
    if experiment.confound_flag or experiment.verdict in {"confounded", "regressed"}:
        return "decayed"
    if experiment.regression_outside_interval:
        # New effect left the prior CI — descriptive drift, not a causal claim.
        if experiment.verdict == "regressed":
            return "decayed"
        return "decaying"
    if experiment.verdict in {"improved", "no_effect"} and experiment.measured_at:
        try:
            measured = datetime.fromisoformat(experiment.measured_at.replace("Z", "+00:00"))
        except ValueError:
            return "unknown"
        interval = max(1, int(experiment.eval_interval_days or DECAY_DAYS))
        age = current - measured
        if age > timedelta(days=interval * 2):
            return "decayed"
        if age > timedelta(days=interval):
            return "decaying"
        return "healthy"
    return "unknown"


def effect_outside_interval(
    *,
    prior_low: float | None,
    prior_high: float | None,
    new_effect: float | None,
) -> bool:
    """True when a new point estimate leaves the prior confidence interval."""
    if prior_low is None or prior_high is None or new_effect is None:
        return False
    low, high = (prior_low, prior_high) if prior_low <= prior_high else (prior_high, prior_low)
    return new_effect < low or new_effect > high


def snapshot_verdict(
    experiment: Experiment, *, at: str | None = None
) -> VerdictHistoryEntry | None:
    """Capture the current measured verdict before overwrite."""
    if experiment.verdict is None and experiment.effect_estimate is None:
        return None
    stamp = (
        at
        or experiment.measured_at
        or experiment.last_evaluated_at
        or datetime.now(UTC).isoformat()
    )
    return VerdictHistoryEntry(
        at=stamp,
        verdict=experiment.verdict,
        plain_verdict=experiment.plain_verdict,
        effect_estimate=experiment.effect_estimate,
        effect_ci_low=experiment.effect_ci_low,
        effect_ci_high=experiment.effect_ci_high,
        sample_size=experiment.outcome_n_effective,
        outcome_n_raw=experiment.outcome_n_raw,
        decay_state=experiment.decay_state,
        regression_outside_interval=experiment.regression_outside_interval,
    )


def experiment_is_due(experiment: Experiment, *, now: datetime | None = None) -> bool:
    """Whether opportunistic re-evaluation is due for a portfolio experiment."""
    if experiment.status not in PORTFOLIO_REEVAL_STATUSES:
        return False
    current = now or datetime.now(UTC)
    if experiment.last_evaluated_at is None and experiment.measured_at is None:
        return experiment.status in {"applied", "measuring"}
    stamp = experiment.last_evaluated_at or experiment.measured_at
    if stamp is None:
        return True
    try:
        last = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return True
    interval = max(1, int(experiment.eval_interval_days or DECAY_DAYS))
    return current - last >= timedelta(days=interval)


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
    apply_entries(
        target,
        [entry],
        backup_dir=backup_dir,
        repo_root=repo_root,
        backup_key=experiment.experiment_id,
    )
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
    revert_from_backup(target, backup, repo_root=repo_root)
    now = datetime.now(UTC).isoformat()
    updated = experiment.model_copy(
        update={
            "status": "reverted",
            "measured_at": now,
            "decay_state": "decayed",
            "last_evaluated_at": now,
            "plain_verdict": (
                "Rule reverted from the managed instruction file; no active effect claim."
            ),
        }
    )
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
    source_rows: list[sqlite3.Row] = []
    if post_trace_ids:
        placeholders = ",".join("?" for _ in post_trace_ids)
        source_rows = conn.execute(
            f"SELECT DISTINCT source FROM traces WHERE trace_id IN ({placeholders})",
            post_trace_ids,
        ).fetchall()
    sources = sorted(str(row["source"]) for row in source_rows)
    agent_type = sources[0] if len(sources) == 1 else "mixed"
    gated = n_eff < float(experiment.min_holdout)
    if gated:
        now = datetime.now(UTC).isoformat()
        updated = experiment.model_copy(
            update={
                "status": "measuring",
                "baseline_n_raw": len(pre_trace_ids),
                "outcome_n_raw": len(post_trace_ids),
                "outcome_n_effective": n_eff,
                "agent_type": agent_type,
                "last_evaluated_at": now,
            }
        )
        ExperimentRepo.update(conn, updated)
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
        effective_n=n_eff,
    )
    now_dt = datetime.now(UTC)
    now = now_dt.isoformat()
    notes = list(causal.data_notes)
    history = list(experiment.effect_history)
    if causal.effect_estimate is not None:
        history.append(float(causal.effect_estimate))
    verdict_history = list(experiment.verdict_history)
    prior = snapshot_verdict(experiment, at=experiment.measured_at or now)
    if prior is not None:
        verdict_history = [*verdict_history, prior][-MAX_VERDICT_HISTORY:]
    outside = effect_outside_interval(
        prior_low=experiment.effect_ci_low,
        prior_high=experiment.effect_ci_high,
        new_effect=causal.effect_estimate,
    )
    if outside:
        notes.append(
            "New effect estimate left the prior confidence interval "
            f"[{experiment.effect_ci_low}, {experiment.effect_ci_high}]; "
            "descriptive drift only, not a causal claim."
        )
    plain = plain_verdict_text(
        verdict=causal.verdict,
        effect_estimate=causal.effect_estimate,
        confound_flag=causal.confound_flag,
        confound_notes=notes,
    )
    if outside:
        plain = f"{plain} Re-evaluation found the estimate outside the prior interval."
    draft = experiment.model_copy(
        update={
            "status": "verdict",
            "outcome_n_effective": n_eff,
            "baseline_n_raw": len(pre_trace_ids),
            "outcome_n_raw": len(post_trace_ids),
            "effect_estimate": causal.effect_estimate,
            "effect_ci_low": causal.effect_ci_low,
            "effect_ci_high": causal.effect_ci_high,
            "test_method": causal.test_method,
            "verdict": causal.verdict,
            "confound_flag": causal.confound_flag,
            "measured_at": now,
            "agent_type": agent_type,
            "plain_verdict": plain,
            "confound_notes": notes,
            "effect_history": history,
            "verdict_history": verdict_history,
            "regression_outside_interval": outside,
            "last_evaluated_at": now,
        }
    )
    updated = draft.model_copy(update={"decay_state": evaluate_decay(draft, now=now_dt)})
    ExperimentRepo.update(conn, updated)
    return MeasureResult(
        experiment_id=experiment.experiment_id,
        verdict=causal.verdict,
        effect_estimate=causal.effect_estimate,
        n_effective=n_eff,
        gated=False,
    )


def waste_rate_metric(conn: sqlite3.Connection, trace_id: str) -> float:
    row = conn.execute(
        "SELECT waste_tokens, input_tokens FROM traces WHERE trace_id = ?",
        (trace_id,),
    ).fetchone()
    if row is None:
        return 0.0
    inp = int(row["input_tokens"] or 0)
    waste = int(row["waste_tokens"] or 0)
    return waste / inp if inp else 0.0


def refresh_portfolio_decay(conn: sqlite3.Connection, *, now: datetime | None = None) -> int:
    """Refresh descriptive decay labels without re-measuring."""
    current = now or datetime.now(UTC)
    updated_n = 0
    for experiment in ExperimentRepo.iter_all(conn):
        if experiment.status in {"proposed", "rejected"}:
            continue
        decay = evaluate_decay(experiment, now=current)
        if decay != experiment.decay_state:
            ExperimentRepo.update(conn, experiment.model_copy(update={"decay_state": decay}))
            updated_n += 1
    return updated_n


def reevaluate_due_experiments(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    now: datetime | None = None,
    force: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    """Opportunistic local re-evaluation — no daemon; sync/recap/CLI only.

    Due portfolio rules are re-measured when holdout traffic exists. Historical
    verdicts are preserved. Decay labels refresh for the whole portfolio.
    """
    current = now or datetime.now(UTC)
    decay_refreshed = refresh_portfolio_decay(conn, now=current)
    due: list[Experiment] = []
    for experiment in ExperimentRepo.iter_all(conn):
        if experiment.status not in PORTFOLIO_REEVAL_STATUSES:
            continue
        if force or experiment_is_due(experiment, now=current):
            due.append(experiment)
        if len(due) >= limit:
            break

    evaluated: list[dict[str, Any]] = []
    for experiment in due:
        # Re-read after decay refresh so we mutate the latest row.
        latest = ExperimentRepo.get(conn, experiment.experiment_id) or experiment
        prior_ci = (latest.effect_ci_low, latest.effect_ci_high)
        prior_snapshot = snapshot_verdict(latest)
        trace_ids = [
            str(row["trace_id"])
            for row in conn.execute(
                """
                SELECT trace_id FROM traces
                WHERE workspace_id = ?
                ORDER BY started_at DESC
                LIMIT 40
                """,
                (workspace_id,),
            ).fetchall()
        ]
        if len(trace_ids) < 2:
            stamp = current.isoformat()
            history = list(latest.verdict_history)
            if prior_snapshot is not None:
                history = [*history, prior_snapshot][-MAX_VERDICT_HISTORY:]
            updated = latest.model_copy(
                update={
                    "last_evaluated_at": stamp,
                    "verdict_history": history,
                    "decay_state": evaluate_decay(
                        latest.model_copy(update={"last_evaluated_at": stamp}),
                        now=current,
                    ),
                    "plain_verdict": (
                        latest.plain_verdict
                        or "Re-evaluation skipped: insufficient local sessions."
                    ),
                }
            )
            ExperimentRepo.update(conn, updated)
            evaluated.append(
                {
                    "experiment_id": latest.experiment_id,
                    "action": "decay_only",
                    "verdict": latest.verdict,
                    "regression_outside_interval": latest.regression_outside_interval,
                }
            )
            continue

        mid = max(1, len(trace_ids) // 2)
        result = measure_experiment(
            conn,
            latest,
            pre_trace_ids=trace_ids[mid:],
            post_trace_ids=trace_ids[:mid],
            metric_fn=lambda tid, _conn=conn: waste_rate_metric(_conn, tid),
        )
        after = ExperimentRepo.get(conn, latest.experiment_id) or latest
        evaluated.append(
            {
                "experiment_id": after.experiment_id,
                "action": "measured" if not result.gated else "gated",
                "verdict": result.verdict,
                "effect_estimate": result.effect_estimate,
                "n_effective": result.n_effective,
                "regression_outside_interval": after.regression_outside_interval,
                "prior_ci": list(prior_ci),
                "decay_state": after.decay_state,
            }
        )

    return {
        "evaluated": evaluated,
        "evaluated_count": len(evaluated),
        "decay_refreshed": decay_refreshed,
        "force": force,
        "daemon": False,
        "limitation": (
            "Opportunistic local re-evaluation only — Cairn does not run a monthly daemon. "
            "Outside-interval flags compare a new estimate to the prior CI and are descriptive."
        ),
    }
