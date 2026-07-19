"""Opportunistic portfolio re-evaluation (T05-04)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from typer.testing import CliRunner

from server.cli import app
from server.improve.experiments import (
    effect_outside_interval,
    evaluate_decay,
    experiment_is_due,
    reevaluate_due_experiments,
    snapshot_verdict,
)
from server.models.evidence import Evidence
from server.models.experiment import Experiment
from server.store.db import Database
from server.store.repos.evidence import EvidenceRepo
from server.store.repos.experiments import ExperimentRepo
from server.util.ids import new_ulid


def _evidence(conn, *, evidence_id: str = "ev1") -> Evidence:
    row = Evidence(
        evidence_id=evidence_id,
        producer="test:optimize-reeval",
        produced_at=datetime.now(UTC).isoformat(),
        trace_ids=[],
        metrics={},
    )
    EvidenceRepo.create(conn, row)
    return row


def _exp(**overrides: object) -> Experiment:
    base = dict(
        experiment_id=new_ulid(),
        created_at="2026-01-01T00:00:00+00:00",
        target_file="AGENTS.md",
        block_key="rule/test",
        kind="instruction",
        content="Do not retry blindly.",
        evidence_id="ev1",
        status="verdict",
        min_holdout=2,
        verdict="improved",
        effect_estimate=-0.1,
        effect_ci_low=-0.2,
        effect_ci_high=-0.05,
        outcome_n_effective=10.0,
        measured_at="2026-06-01T00:00:00+00:00",
        last_evaluated_at="2026-06-01T00:00:00+00:00",
        eval_interval_days=30,
        decay_state="healthy",
        plain_verdict="Holdout evidence suggests improvement.",
    )
    base.update(overrides)
    return Experiment(**base)  # type: ignore[arg-type]


def test_effect_outside_interval_and_snapshot() -> None:
    assert effect_outside_interval(prior_low=-0.2, prior_high=-0.05, new_effect=0.1)
    assert not effect_outside_interval(prior_low=-0.2, prior_high=-0.05, new_effect=-0.1)
    snap = snapshot_verdict(_exp())
    assert snap is not None
    assert snap.verdict == "improved"
    assert snap.sample_size == 10.0


def test_experiment_is_due_respects_interval() -> None:
    now = datetime(2026, 7, 18, tzinfo=UTC)
    fresh = _exp(last_evaluated_at=(now - timedelta(days=5)).isoformat())
    stale = _exp(last_evaluated_at=(now - timedelta(days=40)).isoformat())
    assert not experiment_is_due(fresh, now=now)
    assert experiment_is_due(stale, now=now)


def test_evaluate_decay_uses_outside_interval_flag() -> None:
    outside = _exp(regression_outside_interval=True, verdict="improved")
    assert evaluate_decay(outside) == "decaying"
    regressed = _exp(regression_outside_interval=True, verdict="regressed")
    assert evaluate_decay(regressed) == "decayed"


def test_reevaluate_due_preserves_history(tmp_path) -> None:
    db = Database(tmp_path / "cairn.db")
    conn = db.reader
    ws = new_ulid()
    conn.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) VALUES (?, ?, ?, ?)",
        (ws, str(tmp_path), "reeval", datetime.now(UTC).isoformat()),
    )
    ev = _evidence(conn, evidence_id=new_ulid())
    now = datetime.now(UTC)
    for i in range(6):
        conn.execute(
            """
            INSERT INTO traces (
              trace_id, workspace_id, source, external_id, started_at, status,
              input_tokens, waste_tokens, cost, cost_source
            ) VALUES (?, ?, 'codex', ?, ?, 'completed', 1000, ?, 0.5, 'observed')
            """,
            (
                f"t-{i}",
                ws,
                f"t-{i}",
                (now - timedelta(hours=i)).isoformat(),
                100 + i * 10,
            ),
        )
    exp = _exp(
        evidence_id=ev.evidence_id,
        last_evaluated_at=(now - timedelta(days=40)).isoformat(),
        measured_at=(now - timedelta(days=40)).isoformat(),
        min_holdout=2,
    )
    ExperimentRepo.create(conn, exp)
    conn.commit()

    result = reevaluate_due_experiments(conn, workspace_id=ws, force=False)
    conn.commit()
    assert result["daemon"] is False
    assert result["evaluated_count"] >= 1
    updated = ExperimentRepo.get(conn, exp.experiment_id)
    assert updated is not None
    assert updated.last_evaluated_at is not None
    assert len(updated.verdict_history) >= 1
    assert updated.verdict_history[0].verdict == "improved"
    db.close()


def test_optimize_evaluate_cli(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".cairn").mkdir()
    db = Database(workspace / ".cairn" / "cairn.db")
    ws = new_ulid()
    db.reader.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) VALUES (?, ?, ?, ?)",
        (ws, str(workspace), "cli", datetime.now(UTC).isoformat()),
    )
    ev = _evidence(db.reader, evidence_id=new_ulid())
    ExperimentRepo.create(
        db.reader,
        _exp(
            evidence_id=ev.evidence_id,
            status="applied",
            verdict=None,
            effect_estimate=None,
            measured_at=None,
            last_evaluated_at=None,
            decay_state="unknown",
        ),
    )
    db.reader.commit()
    db.close()
    monkeypatch.chdir(workspace)
    runner = CliRunner()
    result = runner.invoke(app, ["optimize", "evaluate", "--json", "--workspace", str(workspace)])
    assert result.exit_code == 0, result.output
    assert '"daemon": false' in result.output
