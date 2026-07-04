"""Pillar 3 tests — git signals, intent labeler, quality tiers, Lucky-Pass, cost_per_success."""

from __future__ import annotations

import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cairn.outcomes.git import capture_git_signals
from cairn.outcomes.score import (
    agent_quality_score,
    cost_per_success,
    is_lucky_pass,
    label_intent_stages,
    process_quality_score,
)
from cairn.outcomes.tests import run_tests
from cairn.outcomes.tests import test_command_for as get_test_command


def _git_repo() -> Path:
    d = Path(tempfile.mkdtemp())
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    (d / "a.py").write_text("print(1)\n")
    subprocess.run(["git", "add", "."], cwd=d, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=d, check=True)
    return d


def test_git_signals_commit_landed() -> None:
    d = _git_repo()
    now = datetime.now(UTC)
    started = (now - timedelta(hours=2)).isoformat()
    ended = (now - timedelta(minutes=30)).isoformat()
    (d / "b.py").write_text("x = 2\n")
    subprocess.run(["git", "add", "."], cwd=d, check=True)
    subprocess.run(["git", "commit", "-qm", "feat: add b"], cwd=d, check=True)
    g = capture_git_signals(str(d), started, ended)
    assert g.commit_landed
    assert "b.py" in g.files_changed
    assert g.commit_sha is not None


def test_git_signals_no_cwd_is_unknown() -> None:
    g = capture_git_signals(None, "2026-06-01T00:00:00", "2026-06-01T01:00:00")
    assert g.commit_landed is False
    assert g.data_notes  # has a data-note


def test_git_signals_never_raises_on_bad_repo(tmp_path: Path) -> None:
    g = capture_git_signals(str(tmp_path), "2026-06-01T00:00:00", "2026-06-01T01:00:00")
    assert g.commit_landed is False
    assert any("not a git repo" in n for n in g.data_notes)


def test_intent_stages_labeler() -> None:
    events: list[dict] = []
    seq = 1

    def add(t, norm=None, path=None):
        nonlocal seq
        e = {"type": t, "seq": seq}
        seq += 1
        if norm:
            e["tool_norm_name"] = norm
        if path:
            e["path_rel"] = path
        events.append(e)

    add("user_prompt")
    add("tool_call", "read", "a.py")  # Exploration (no edit yet)
    add("tool_call", "search", "a.py")  # Exploration
    add("tool_call", "edit", "a.py")  # Implementation
    add("tool_call", "read", "a.py")  # Verification (edit happened)
    add("tool_call", "sub_agent")  # Orchestration
    labels = dict(label_intent_stages(events))
    assert labels[2] == "Exploration"
    assert labels[3] == "Exploration"
    assert labels[4] == "Implementation"
    assert labels[5] == "Verification"
    assert labels[6] == "Orchestration"


def test_quality_score_in_range_and_weights() -> None:
    q = agent_quality_score(
        commit_landed=True,
        tests_passed=5,
        tests_failed=1,
        build_status="pass",
        waste_tokens=100,
        total_tokens=1000,
        peak_context_pct=40.0,
        context_rot_penalty=1.0,
        retry_rate=0.1,
        error_rate=0.05,
        mahalanobis_distance=2.0,
        drift_threshold=11.345,
    )
    assert 0.0 <= q.score <= 100.0
    # success component should be 1.0 (commit + tests pass).
    assert q.components["success"] == 1.0
    # weights sum to 1.0.
    assert abs(sum(q.weights.values()) - 1.0) < 1e-9


def test_lucky_pass_flag_on_brittle_commit() -> None:
    events: list[dict] = []
    seq = 1

    def add(t, norm=None, path=None):
        nonlocal seq
        e = {"type": t, "seq": seq}
        seq += 1
        if norm:
            e["tool_norm_name"] = norm
        if path:
            e["path_rel"] = path
        events.append(e)

    # verify→implement→explore cyclic pattern → Lucky.
    for _ in range(3):
        add("user_prompt")
        add("tool_call", "edit", "a.py")
        add("tool_call", "read", "a.py")
        add("tool_call", "edit", "a.py")
        add("tool_call", "read", "a.py")
        add("assistant_message")
    p = process_quality_score(events)
    assert p.tier == "Lucky"
    assert is_lucky_pass(p, commit_landed=True) is True
    assert is_lucky_pass(p, commit_landed=False) is False


def test_ideal_tier_for_clean_explore_implement_verify() -> None:
    events: list[dict] = []
    seq = 1

    def add(t, norm=None, path=None):
        nonlocal seq
        e = {"type": t, "seq": seq}
        seq += 1
        if norm:
            e["tool_norm_name"] = norm
        if path:
            e["path_rel"] = path
        events.append(e)

    add("user_prompt")
    add("tool_call", "read", "a.py")
    add("tool_call", "search", "a.py")
    add("tool_call", "edit", "a.py")
    add("tool_call", "read", "a.py")
    add("assistant_message")
    p = process_quality_score(events)
    assert p.tier in ("Ideal", "Solid")
    assert p.score >= 47


def test_cost_per_success_excludes_lucky_with_div0_guard() -> None:
    cps = cost_per_success(
        [
            {"total_cost": 1.0, "commit_landed": True, "lucky_pass": False},
            {"total_cost": 2.0, "commit_landed": True, "lucky_pass": True},  # excluded
            {"total_cost": 3.0, "commit_landed": True, "lucky_pass": False},
        ]
    )
    assert cps["cost_per_success"] == 2.0
    assert cps["non_lucky_successes"] == 2
    assert cps["variance"] is not None
    # div0 guard → NULL + data-note.
    empty = cost_per_success([])
    assert empty["cost_per_success"] is None
    assert empty["data_notes"]


def test_command_opt_in_default_off(tmp_path: Path, monkeypatch) -> None:
    # Point the config path at a non-existent file → no test_command.
    monkeypatch.setattr("cairn.config.CONFIG_PATH", tmp_path / "none.toml")
    monkeypatch.setattr("cairn.config.CONFIG_DIR", tmp_path)
    assert get_test_command("myproject") is None
    tr = run_tests(str(tmp_path), "myproject")
    assert tr.status == "unknown"
    assert tr.build_status == "unknown"
    assert any("configure test_command" in n for n in tr.data_notes)


def test_command_opt_in_runs_when_configured(tmp_path: Path, monkeypatch) -> None:
    cfg_dir = tmp_path / "cfg" / ".cairn"
    cfg_dir.mkdir(parents=True)
    script = tmp_path / "t.py"
    script.write_text("print('3 passed, 0 warnings in 0.1s')\n")
    cfg = cfg_dir / "config.toml"
    cfg.write_text(f'[tests]\ndefault = "python3 {script.as_posix()}"\n')
    monkeypatch.setattr("cairn.config.CONFIG_PATH", cfg)
    monkeypatch.setattr("cairn.config.CONFIG_DIR", cfg_dir)
    cmd = get_test_command("anyproject")
    assert cmd is not None
    tr = run_tests(str(tmp_path), "anyproject")
    assert tr.status == "pass"
    assert tr.tests_passed == 3
    assert tr.build_status == "pass"
