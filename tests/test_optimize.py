"""Optimize proposals and managed block apply."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from cairn.ledger.ledger import Ledger
from cairn.optimize.apply import Entry, ProposalRecord, apply_proposals, preview_diff
from cairn.optimize.engine import generate_proposals
from cairn.optimize.impact import (
    DEFAULT_K,
    Bandit,
    _composite_reward,
    measure_rule,
    run_measurement,
    verdict_for,
)


def test_optimize_proposals_and_apply(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "wasteful_session.jsonl"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_jsonl_file(fixture, repo_root=root)
    writer = CaptureWriter(root)
    try:
        writer.ingest_claude_session(parsed)
        conn = writer.connection
        proposals = generate_proposals(conn, root, days=3650)
        assert proposals
        diff = preview_diff(root, proposals)
        assert diff
        result = apply_proposals(root, proposals, force=True)
        assert result.applied >= 1
        text = (root / "AGENTS.md").read_text(encoding="utf-8")
        assert "cairn:managed" in text
    finally:
        writer.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _day(offset: int) -> str:
    return (datetime.now(UTC) - timedelta(days=offset)).isoformat()


def _future(minutes: int = 5) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def _open(root: Path) -> tuple[Ledger, sqlite3.Connection]:
    ledger = Ledger(root / ".cairn" / "ledger.db")
    return ledger, ledger.connection


def _seed_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    started_at: str | None = None,
    project: str = "proj",
    cost: float = 1.0,
) -> None:
    conn.execute(
        """
        INSERT INTO runs (run_id, source, external_id, started_at, ended_at,
            status, total_cost, total_input_tokens, total_output_tokens, has_cost, project)
        VALUES (?, 'claude-code', ?, ?, ?, 'completed', ?, 1000, 100, 1, ?)
        """,
        (run_id, run_id, started_at or _now(), started_at or _now(), cost, project),
    )


def _seed_read(conn: sqlite3.Connection, run_id: str, seq: int, path: str) -> None:
    conn.execute(
        "INSERT INTO events (run_id, seq, type, tool_norm_name, path_rel) "
        "VALUES (?, ?, 'tool_call', 'read', ?)",
        (run_id, seq, path),
    )


# ---------------------------------------------------------------------------
# ≥2 candidate rewrites, strongest evidence picked
# ---------------------------------------------------------------------------


def test_proposals_have_two_plus_candidates_strongest_picked(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    ledger, conn = _open(root)
    try:
        _seed_run(conn, "r1", started_at=_day(1))
        # 3 identical grep calls with the same text_inline + text_hash.
        for seq in range(1, 4):
            conn.execute(
                "INSERT INTO events (run_id, seq, type, tool_norm_name, text_inline, text_hash) "
                "VALUES ('r1', ?, 'tool_call', 'search', 'find foo bar', 'h1')",
                (seq,),
            )
        conn.commit()
        proposals = generate_proposals(conn, root, days=14)
    finally:
        ledger.close()
    assert proposals, "expected at least one proposal"
    rule = next(p for p in proposals if p.entry.kind == "rule")
    assert len(rule.candidates) >= 2
    # The selected rewrite must name the concrete evidence ("foo"), not the
    # vague "X" placeholder candidate.
    assert "foo" in rule.entry.content
    assert "foo" in rule.candidates[rule.selected_index]
    assert rule.evidence.get("evidence_type") == "identical_grep"


# ---------------------------------------------------------------------------
# Apply: managed block only, user content untouched, backup created
# ---------------------------------------------------------------------------


def test_apply_creates_backup_and_preserves_user_content(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "AGENTS.md").write_text("# My project\n\nHuman notes here.\n", encoding="utf-8")
    ledger, conn = _open(root)
    try:
        _seed_run(conn, "r1", started_at=_day(1))
        for seq in range(1, 5):
            _seed_read(conn, "r1", seq, "src/main.py")
        conn.commit()
        proposals = generate_proposals(conn, root, days=14)
    finally:
        ledger.close()
    assert proposals
    result = apply_proposals(root, proposals, force=True)
    assert result.applied >= 1
    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Human notes here." in text  # user content preserved
    assert "cairn:managed" in text
    backups = list((root / ".cairn" / "backups").glob("AGENTS.md.*.bak"))
    assert backups, "expected a backup before write"


# ---------------------------------------------------------------------------
# Holdout measurement: pool != holdout, proposer never sees holdout
# ---------------------------------------------------------------------------


def _apply_file_guide(root: Path, path: str = "src/main.py") -> str:
    """Apply a single file_guide rule and return its block_key (entry_id)."""
    ledger, conn = _open(root)
    try:
        _seed_run(conn, "pre1", started_at=_day(5))
        for seq in range(1, 9):
            _seed_read(conn, "pre1", seq, path)
        conn.commit()
        record = ProposalRecord(
            op="add",
            entry=Entry(kind="file_guide", entry_id="fg_main", content=f"`{path}`: main entry."),
            evidence={"path": path, "reads": 8, "evidence_type": "repeated_file_reads"},
            source="test",
        )
    finally:
        ledger.close()
    apply_proposals(root, [record], force=True)
    return "fg_main"


def test_measurement_holdout_disjoint_from_pool(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    block_key = _apply_file_guide(root)
    # 10 post-apply sessions with 0 reads → outcome 0 < baseline 8 → improved.
    ledger, conn = _open(root)
    try:
        for i in range(10):
            _seed_run(conn, f"post{i}", started_at=_future(i + 1))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM optimizations WHERE block_key = ?", (block_key,)
        ).fetchone()
        assert row is not None
        res = measure_rule(conn, row, m=10)
    finally:
        ledger.close()
    assert res.verdict == "improved"
    assert set(res.proposal_pool) & set(res.holdout) == set()
    assert res.proposal_pool != res.holdout
    assert res.outcome_sessions >= 10


def test_measurement_insufficient_below_m(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    block_key = _apply_file_guide(root)
    ledger, conn = _open(root)
    try:
        for i in range(3):  # < M=10
            _seed_run(conn, f"post{i}", started_at=_future(i + 1))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM optimizations WHERE block_key = ?", (block_key,)
        ).fetchone()
        res = measure_rule(conn, row, m=10)
    finally:
        ledger.close()
    assert res.verdict == "insufficient"


# ---------------------------------------------------------------------------
# Thompson-sampling bandit
# ---------------------------------------------------------------------------


def test_bandit_beta_update_and_prune_threshold() -> None:
    bandit = Bandit()
    # A losing arm: 3 holds with reward 0 → posterior P(improve) drops.
    for _ in range(DEFAULT_K):
        bandit.update("loser", 0.0)
    assert bandit.hold_count("loser") >= DEFAULT_K
    p = bandit.p_improve("loser")
    assert 0.0 <= p <= 1.0
    # Prune fires only after K holds with P(improve) < threshold.
    assert "loser" in bandit.prune(k=DEFAULT_K, threshold=0.3)
    # A winning arm: reward 1.0 → high P(improve), never pruned.
    for _ in range(DEFAULT_K):
        bandit.update("winner", 1.0)
    assert "winner" not in bandit.prune(k=DEFAULT_K, threshold=0.2)
    assert bandit.p_improve("winner") > bandit.p_improve("loser")


def test_bandit_select_returns_an_arm() -> None:
    bandit = Bandit()
    choice = bandit.select(["a", "b", "c"])
    assert choice in {"a", "b", "c"}


def test_bandit_reward_composite_and_div0_guard() -> None:
    # waste-down 50% + fp-stable 50% → 0.5
    r = _composite_reward(baseline=10.0, outcome=5.0, fp_baseline=2.0, fp_outcome=1.0)
    assert abs(r - 0.5) < 1e-6
    # div0 guard: baseline 0, outcome 0 → no fabrication, neutral fp.
    r0 = _composite_reward(baseline=0.0, outcome=0.0, fp_baseline=None, fp_outcome=None)
    assert 0.0 <= r0 <= 1.0


def test_verdict_for_div0_and_band() -> None:
    assert verdict_for(0, 0) == "no_effect"
    assert verdict_for(0, 5) == "regressed"
    assert verdict_for(10, 5) == "improved"  # 5 < 9
    assert verdict_for(10, 9.5) == "no_effect"  # within ±10%
    assert verdict_for(10, 12) == "regressed"  # 12 > 11
    # Fingerprint distance must shrink for "improved".
    assert verdict_for(10, 5, fp_baseline=1.0, fp_outcome=2.0) == "regressed"


# ---------------------------------------------------------------------------
# fingerprint_distance used as a metric + auto-revert on regressed
# ---------------------------------------------------------------------------


def test_fingerprint_distance_recorded_as_baseline(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    ledger, conn = _open(root)
    try:
        _seed_run(conn, "r1", started_at=_day(5))
        _seed_read(conn, "r1", 1, "src/main.py")
        # Insert a fingerprint for the run so the baseline helper has data.
        vec = [0.1] * 24
        conn.execute(
            "INSERT INTO fingerprints (run_id, project, model, source, ts, vector_json, week) "
            "VALUES ('r1', 'proj', 'claude-opus', 'claude-code', ?, ?, '2026-W24')",
            (_day(5), json.dumps(vec)),
        )
        conn.commit()
        record = ProposalRecord(
            op="add",
            entry=Entry(kind="file_guide", entry_id="fg_main", content="`src/main.py`: main."),
            evidence={"path": "src/main.py", "evidence_type": "repeated_file_reads"},
        )
    finally:
        ledger.close()
    apply_proposals(root, [record], force=True)
    ledger, conn = _open(root)
    try:
        row = conn.execute(
            "SELECT baseline_sessions, fingerprint_distance_baseline FROM optimizations "
            "WHERE block_key = 'fg_main'"
        ).fetchone()
    finally:
        ledger.close()
    assert row["baseline_sessions"] is not None and row["baseline_sessions"] >= 1


def test_auto_revert_on_regressed(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    block_key = _apply_file_guide(root)
    # 10 post-apply sessions each re-reading src/main.py once → outcome 10 >
    # baseline 8 * 1.1 → regressed → auto-revert.
    ledger, conn = _open(root)
    try:
        for i in range(10):
            _seed_run(conn, f"post{i}", started_at=_future(i + 1))
            _seed_read(conn, f"post{i}", 1, "src/main.py")
        conn.commit()
    finally:
        ledger.close()
    summary = run_measurement(root, m=10)
    pruned = summary.get("pruned", [])
    assert block_key in pruned
    # The managed block no longer contains the regressed entry.
    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "fg_main" not in text
    ledger, conn = _open(root)
    try:
        status = conn.execute(
            "SELECT status FROM optimizations WHERE block_key = ?", (block_key,)
        ).fetchone()["status"]
    finally:
        ledger.close()
    assert status == "pruned"


def test_run_measurement_updates_bandit_posterior(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    block_key = _apply_file_guide(root)
    ledger, conn = _open(root)
    try:
        for i in range(10):
            _seed_run(conn, f"post{i}", started_at=_future(i + 1))
        conn.commit()
    finally:
        ledger.close()
    summary = run_measurement(root, m=10)
    verdicts = {v["block_key"]: v for v in summary["verdicts"]}
    assert block_key in verdicts
    assert verdicts[block_key]["verdict"] == "improved"
    # The bandit persisted an updated posterior for the arm.
    bandit_state = summary.get("bandit", {})
    assert block_key in bandit_state
    assert bandit_state[block_key]["holds"] >= 1
    assert bandit_state[block_key]["p_improve"] > 0.5
