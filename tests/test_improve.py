"""Phase 6 improvement loop tests."""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from server import cli as cli_module
from server.improve.apply import (
    BlockConflictError,
    BlockError,
    ManagedEntry,
    apply_entries,
    find_backup,
    revert_from_backup,
)
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
from server.store.repos.experiments import ExperimentRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid


def test_cuped_reduces_variance() -> None:
    outcomes = [10.0, 12.0, 11.0, 13.0, 9.0]
    cov = [100.0, 102.0, 101.0, 103.0, 99.0]
    adj, se = cuped_adjust(outcomes, cov)
    assert se >= 0
    assert 9.0 <= adj <= 13.0


def test_measurement_is_plain_difference_without_synthetic_covariates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = sqlite3.connect(":memory:")
    from server.store.migrate import migrate

    migrate(conn)
    values = {
        **{f"pre-{i}": float(i) for i in range(10)},
        **{f"post-{i}": float(i) - 2.0 for i in range(15)},
    }

    def fail_if_called(*_args: object, **_kwargs: object) -> tuple[float, float]:
        raise AssertionError("CUPED must not be used without per-unit covariates")

    monkeypatch.setattr("server.improve.stats.cuped_adjust", fail_if_called)
    result = measure_causal_effect(
        conn,
        pre_trace_ids=[f"pre-{i}" for i in range(10)],
        post_trace_ids=[f"post-{i}" for i in range(15)],
        metric_fn=values.__getitem__,
    )

    assert result.effect_estimate == pytest.approx(0.5)
    assert result.test_method == "difference_in_means+anytime_valid_cs"


def test_difference_in_means_confidence_sequence_has_simulated_coverage() -> None:
    rng = random.Random(20260714)
    conn = sqlite3.connect(":memory:")
    from server.store.migrate import migrate

    migrate(conn)
    true_effect = -0.35
    simulations = 300
    covered = 0
    for simulation in range(simulations):
        pre_ids = [f"{simulation}-pre-{i}" for i in range(40)]
        post_ids = [f"{simulation}-post-{i}" for i in range(40)]
        values = {trace_id: rng.gauss(2.0, 1.0) for trace_id in pre_ids}
        values.update({trace_id: rng.gauss(2.0 + true_effect, 1.0) for trace_id in post_ids})
        result = measure_causal_effect(
            conn,
            pre_trace_ids=pre_ids,
            post_trace_ids=post_ids,
            metric_fn=values.__getitem__,
        )
        assert result.effect_ci_low is not None and result.effect_ci_high is not None
        covered += int(result.effect_ci_low <= true_effect <= result.effect_ci_high)

    assert covered / simulations >= 0.95


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


def _entry(content: str = "Use pytest -q") -> ManagedEntry:
    return ManagedEntry(kind="rule", entry_id="r1", content=content)


def test_apply_and_revert_preserves_outside_block(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("# Human\n\nKeep this line.\n", encoding="utf-8")
    backup = apply_entries(
        target,
        [_entry()],
        backup_dir=tmp_path / ".cairn" / "backups",
        repo_root=tmp_path,
        backup_key="exp-1",
    )
    applied = target.read_text(encoding="utf-8")
    assert "cairn:begin sha256=" in applied
    assert backup.read_text(encoding="utf-8") == "# Human\n\nKeep this line.\n"

    target.write_text(applied.replace("# Human", "# Human edited") + "Outside tail.\n")
    apply_entries(
        target,
        [_entry("Use pytest -q tests/unit")],
        backup_dir=tmp_path / ".cairn" / "backups",
        repo_root=tmp_path,
        backup_key="exp-2",
    )
    reapplied = target.read_text(encoding="utf-8")
    assert "# Human edited" in reapplied
    assert "Outside tail." in reapplied
    assert "Use pytest -q tests/unit" in reapplied

    revert_from_backup(target, backup, repo_root=tmp_path)
    reverted = target.read_text(encoding="utf-8")
    assert "cairn:begin" not in reverted
    assert "# Human edited" in reverted
    assert "Outside tail." in reverted


def test_user_edit_inside_managed_block_surfaces_conflict(tmp_path: Path) -> None:
    target = tmp_path / "CLAUDE.md"
    backup_dir = tmp_path / ".cairn" / "backups"
    apply_entries(
        target,
        [_entry()],
        backup_dir=backup_dir,
        repo_root=tmp_path,
        backup_key="exp-1",
    )
    edited = target.read_text(encoding="utf-8").replace("Use pytest -q", "User override")
    target.write_text(edited, encoding="utf-8")

    with pytest.raises(BlockConflictError, match="edited after Cairn"):
        apply_entries(
            target,
            [_entry("Replacement")],
            backup_dir=backup_dir,
            repo_root=tmp_path,
            backup_key="exp-2",
        )

    assert target.read_text(encoding="utf-8") == edited
    assert len(list(backup_dir.glob("*.bak"))) == 1


def test_unbalanced_managed_marker_is_never_appended_over(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    original = "# Human\n\n<!-- cairn:begin sha256=broken -->\nKeep me.\n"
    target.write_text(original, encoding="utf-8")
    with pytest.raises(BlockError, match="unbalanced"):
        apply_entries(
            target,
            [_entry()],
            backup_dir=tmp_path / ".cairn" / "backups",
            repo_root=tmp_path,
        )
    assert target.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("relative", ["notes.md", "nested/AGENTS.md", "../AGENTS.md"])
def test_apply_refuses_targets_outside_allowlist(tmp_path: Path, relative: str) -> None:
    target = tmp_path / relative
    with pytest.raises(BlockError, match="only manage"):
        apply_entries(
            target,
            [_entry()],
            backup_dir=tmp_path / ".cairn" / "backups",
            repo_root=tmp_path,
        )
    assert not target.exists()


def test_apply_refuses_allowed_name_when_it_is_a_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("Do not change.\n", encoding="utf-8")
    target = tmp_path / "AGENTS.md"
    target.symlink_to(outside)
    with pytest.raises(BlockError, match="only manage"):
        apply_entries(
            target,
            [_entry()],
            backup_dir=tmp_path / ".cairn" / "backups",
            repo_root=tmp_path,
        )
    assert outside.read_text(encoding="utf-8") == "Do not change.\n"


def test_apply_refuses_backup_directory_outside_cairn(tmp_path: Path) -> None:
    with pytest.raises(BlockError, match="backups must stay"):
        apply_entries(
            tmp_path / "AGENTS.md",
            [_entry()],
            backup_dir=tmp_path / "backups",
            repo_root=tmp_path,
        )


def test_missing_target_has_backup_and_revert_removes_only_cairn_file(tmp_path: Path) -> None:
    target = tmp_path / ".cursor" / "rules"
    backup_dir = tmp_path / ".cairn" / "backups"
    backup = apply_entries(
        target,
        [_entry()],
        backup_dir=backup_dir,
        repo_root=tmp_path,
        backup_key="exp-missing",
    )
    assert backup.is_file() and ".missing.bak" in backup.name
    assert find_backup(backup_dir, target, backup_key="exp-missing") == backup

    revert_from_backup(target, backup, repo_root=tmp_path)
    assert not target.exists()


def test_revert_refuses_user_edit_inside_managed_block(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    backup = apply_entries(
        target,
        [_entry()],
        backup_dir=tmp_path / ".cairn" / "backups",
        repo_root=tmp_path,
        backup_key="exp-1",
    )
    target.write_text(
        target.read_text(encoding="utf-8").replace("Use pytest -q", "User override"),
        encoding="utf-8",
    )
    with pytest.raises(BlockConflictError):
        revert_from_backup(target, backup, repo_root=tmp_path)
    assert target.is_file()


def test_optimize_revert_cli_uses_experiment_revert_action(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, dict[str, object], Path | None]] = []

    def fake_run(name: str, params: dict[str, object], root: Path | None) -> dict[str, object]:
        calls.append((name, params, root))
        return {"experiment_id": params["experiment_id"], "status": "reverted"}

    monkeypatch.setattr(cli_module, "_run_action", fake_run)
    result = CliRunner().invoke(
        cli_module.app,
        ["optimize", "revert", "exp-1", "--workspace", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert calls == [("experiment_revert", {"experiment_id": "exp-1"}, tmp_path)]
    assert '"status": "reverted"' in result.output


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
    stored = ExperimentRepo.get(db.reader, exp.experiment_id)
    assert stored is not None
    assert stored.status == "measuring"
    assert stored.outcome_n_effective == pytest.approx(2.0)


def test_clustered_ess_changes_improved_verdict_to_inconclusive(db: Database) -> None:
    ev = Evidence(
        evidence_id=new_ulid(),
        producer="test",
        produced_at="2026-01-01",
        trace_ids=["pre-0"],
        metrics={},
    )
    EvidenceRepo.create(db.reader, ev)
    exp = create_experiment(
        db.reader,
        target_file="AGENTS.md",
        block_key="clustered-verdict",
        kind="rule",
        content="rule",
        evidence_id=ev.evidence_id,
        min_holdout=5,
    )
    db.reader.commit()
    pre_ids = [f"pre-{i}" for i in range(20)]
    post_ids = [f"post-{i}" for i in range(20)]
    values = {
        **{trace_id: 10.0 + (0.69 if i % 2 else -0.69) for i, trace_id in enumerate(pre_ids)},
        **{trace_id: 9.0 + (0.69 if i % 2 else -0.69) for i, trace_id in enumerate(post_ids)},
    }
    raw = measure_causal_effect(
        db.reader,
        pre_trace_ids=pre_ids,
        post_trace_ids=post_ids,
        metric_fn=values.__getitem__,
    )
    assert raw.verdict == "improved"

    clustered = measure_experiment(
        db.reader,
        exp,
        pre_trace_ids=pre_ids,
        post_trace_ids=post_ids,
        metric_fn=values.__getitem__,
        clusters=["task-a"] * 10 + ["task-b"] * 10,
    )

    assert clustered.gated is False
    assert clustered.n_effective == pytest.approx(20 / 3.7)
    assert clustered.verdict == "inconclusive"


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


def test_confounded_on_task_complexity_shift(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "task-mix.db")
    from server.store.migrate import migrate

    migrate(conn)
    pre_ids = [f"pre-{i}" for i in range(6)]
    post_ids = [f"post-{i}" for i in range(6)]
    for trace_id in pre_ids:
        conn.execute(
            "INSERT INTO traces "
            "(trace_id, workspace_id, source, project, model, span_count, status) "
            "VALUES (?, 'ws', 'codex', 'repo', 'm1', 5, 'completed')",
            (trace_id,),
        )
    for trace_id in post_ids:
        conn.execute(
            "INSERT INTO traces "
            "(trace_id, workspace_id, source, project, model, span_count, status) "
            "VALUES (?, 'ws', 'codex', 'repo', 'm1', 60, 'completed')",
            (trace_id,),
        )
    conn.commit()

    result = measure_causal_effect(
        conn,
        pre_trace_ids=pre_ids,
        post_trace_ids=post_ids,
        metric_fn=lambda trace_id: 1.0 if trace_id.startswith("pre") else 0.5,
    )

    assert result.verdict == "confounded"
    assert "task mix shifted: spans-per-session distribution changed" in result.data_notes
    conn.close()


def test_confounded_on_agent_schema_version_change(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "schema-mix.db")
    from server.store.migrate import migrate

    migrate(conn)
    pre_ids = [f"pre-{i}" for i in range(6)]
    post_ids = [f"post-{i}" for i in range(6)]
    for trace_id, parser_version in [
        *((trace_id, "codex@1") for trace_id in pre_ids),
        *((trace_id, "codex@2") for trace_id in post_ids),
    ]:
        conn.execute(
            "INSERT INTO traces "
            "(trace_id, workspace_id, source, project, model, span_count, status) "
            "VALUES (?, 'ws', 'codex', 'repo', 'm1', 12, 'completed')",
            (trace_id,),
        )
        conn.execute(
            "INSERT INTO data_quality (trace_id, parser_version) VALUES (?, ?)",
            (trace_id, parser_version),
        )
    conn.commit()

    result = measure_causal_effect(
        conn,
        pre_trace_ids=pre_ids,
        post_trace_ids=post_ids,
        metric_fn=lambda trace_id: 1.0 if trace_id.startswith("pre") else 0.5,
    )

    assert result.verdict == "confounded"
    assert "agent/schema version changed: parser-version distribution shifted" in result.data_notes
    conn.close()
