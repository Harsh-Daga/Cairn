"""Phase 6 improvement loop tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from server.improve.apply import ManagedEntry, apply_entries, revert_from_backup
from server.improve.bandit import Bandit
from server.improve.experiments import create_experiment, measure_experiment, preview
from server.improve.stats import (
    anytime_valid_verdict,
    clustered_effective_n,
    cuped_adjust,
    measure_causal_effect,
)
from server.models.evidence import Evidence
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.evidence import EvidenceRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid


def test_cuped_reduces_variance() -> None:
    outcomes = [10.0, 12.0, 11.0, 13.0, 9.0]
    cov = [100.0, 102.0, 101.0, 103.0, 99.0]
    adj, se = cuped_adjust(outcomes, cov)
    assert se >= 0
    assert 9.0 <= adj <= 13.0


def test_anytime_valid_improved_when_ci_below_practical_band() -> None:
    res = anytime_valid_verdict(-0.5, 0.05, n=30, baseline=10.0)
    assert res.verdict == "improved"
    assert res.test_method == "anytime_valid_cs"
    assert res.effect_ci_high is not None and res.effect_ci_high < 0


def test_clustered_ess() -> None:
    values = [1.0] * 20
    clusters = [f"c{i // 4}" for i in range(20)]
    n_eff = clustered_effective_n(values, clusters, rho=0.5)
    assert 7.5 <= n_eff <= 8.5


def test_bandit_selects_arm() -> None:
    bandit = Bandit({"a": (5.0, 1.0), "b": (1.0, 5.0)})
    pick = bandit.select(["a", "b"])
    assert pick in {"a", "b"}


def test_apply_and_revert_preserves_outside_block(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("# Human\n\nKeep this line.\n", encoding="utf-8")
    backup = apply_entries(
        target,
        [ManagedEntry(kind="rule", entry_id="r1", content="Use pytest -q")],
        backup_dir=tmp_path / ".cairn" / "backups",
    )
    assert "cairn:begin" in target.read_text(encoding="utf-8")
    assert "Keep this line." in target.read_text(encoding="utf-8")
    revert_from_backup(target, backup)
    assert target.read_text(encoding="utf-8") == "# Human\n\nKeep this line.\n"


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "cairn.db")
    ws_id = new_ulid()
    WorkspaceRepo.create(
        database.reader,
        Workspace(workspace_id=ws_id, root_path=str(tmp_path), name="t", created_at="2026-01-01"),
    )
    database.reader.commit()
    return database


def test_measure_gated_until_holdout(db: Database) -> None:
    ev = Evidence(
        evidence_id=new_ulid(),
        producer="test",
        produced_at="2026-01-01",
        trace_ids=["t1"],
        metrics={},
    )
    EvidenceRepo.create(db.reader, ev)
    exp = create_experiment(
        db.reader,
        target_file="AGENTS.md",
        block_key="k1",
        kind="rule",
        content="rule",
        evidence_id=ev.evidence_id,
        min_holdout=8,
    )
    db.reader.commit()
    result = measure_experiment(
        db.reader,
        exp,
        pre_trace_ids=["a"],
        post_trace_ids=["b", "c"],
        metric_fn=lambda _tid: 1.0,
        clusters=["c0", "c1"],
    )
    assert result.gated is True
    assert result.verdict == "inconclusive"


def test_preview_estimates_days_from_traffic(db: Database) -> None:
    ws_row = db.reader.execute("SELECT workspace_id FROM workspaces LIMIT 1").fetchone()
    assert ws_row is not None
    ws_id = str(ws_row[0])
    for i in range(14):
        db.reader.execute(
            "INSERT INTO traces (trace_id, workspace_id, source, model, started_at, status) "
            "VALUES (?, ?, 'claude_code', 'm1', date('now', ?), 'completed')",
            (new_ulid(), ws_id, f"-{i} days"),
        )
    ev = Evidence(
        evidence_id=new_ulid(),
        producer="test",
        produced_at="2026-01-01",
        trace_ids=["t1"],
        metrics={},
    )
    EvidenceRepo.create(db.reader, ev)
    exp = create_experiment(
        db.reader,
        target_file="AGENTS.md",
        block_key="k2",
        kind="rule",
        content="rule",
        evidence_id=ev.evidence_id,
        min_holdout=8,
    )
    db.reader.commit()
    result = preview(db.reader, exp, workspace_id=ws_id)
    assert result.traces_per_day == 1.0
    assert result.n_effective_needed == 8.0
    assert result.expected_days_to_verdict == 8.0
    assert result.traffic_unknown is False


def test_preview_unknown_on_low_traffic(db: Database) -> None:
    ws_row = db.reader.execute("SELECT workspace_id FROM workspaces LIMIT 1").fetchone()
    assert ws_row is not None
    ws_id = str(ws_row[0])
    ev = Evidence(
        evidence_id=new_ulid(),
        producer="test",
        produced_at="2026-01-01",
        trace_ids=["t1"],
        metrics={},
    )
    EvidenceRepo.create(db.reader, ev)
    exp = create_experiment(
        db.reader,
        target_file="AGENTS.md",
        block_key="k3",
        kind="rule",
        content="rule",
        evidence_id=ev.evidence_id,
        min_holdout=8,
    )
    db.reader.commit()
    result = preview(db.reader, exp, workspace_id=ws_id)
    assert result.traffic_unknown is True
    assert result.expected_days_to_verdict is None


def test_confounded_on_model_mix_shift(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "c.db")
    from server.store.migrate import migrate

    migrate(conn)
    conn.execute(
        "INSERT INTO traces (trace_id, workspace_id, source, model, started_at, status) "
        "VALUES ('t1','ws','claude_code','m1','2026-01-01','completed')"
    )
    conn.execute(
        "INSERT INTO traces (trace_id, workspace_id, source, model, started_at, status) "
        "VALUES ('t2','ws','claude_code','m2','2026-01-02','completed')"
    )
    conn.commit()

    def metric(tid: str) -> float:
        return 0.1 if tid == "t1" else 0.2

    res = measure_causal_effect(conn, pre_trace_ids=["t1"], post_trace_ids=["t2"], metric_fn=metric)
    assert res.verdict == "confounded"
    conn.close()
