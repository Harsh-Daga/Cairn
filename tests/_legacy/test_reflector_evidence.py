"""Tests for reflector evidence resolution and impact scoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from cairn.ledger.ledger import Ledger
from cairn.optimize.apply import Entry, ProposalRecord, apply_proposals
from cairn.optimize.impact import classify, compute_outcomes
from cairn.optimize.reflector import Proposal, resolve_evidence


def test_resolve_evidence_file_guide() -> None:
    p = Proposal(
        op="add",
        kind="file_guide",
        entry_id="fg1",
        content="guide",
        evidence_refs=["src/app.py", "src/other.py"],
    )
    assert resolve_evidence(p) == {"path": "src/app.py"}


def test_resolve_evidence_file_guide_no_refs() -> None:
    p = Proposal(op="add", kind="file_guide", entry_id="fg1", content="guide")
    assert resolve_evidence(p) == {"path": ""}


def test_resolve_evidence_command_fix() -> None:
    p = Proposal(
        op="add",
        kind="command_fix",
        entry_id="cf1",
        content="fix",
        evidence_refs=["bad_cmd --flag"],
    )
    ev = resolve_evidence(p)
    assert ev["bad"] == "bad_cmd --flag"
    assert ev["name"] == "bad_cmd --flag"
    assert ev["tool_name"] == "bad_cmd --flag"


def test_resolve_evidence_known_issue() -> None:
    p = Proposal(
        op="add",
        kind="known_issue",
        entry_id="ki1",
        content="issue",
        evidence_refs=["failing_tool"],
    )
    ev = resolve_evidence(p)
    assert ev["tool_name"] == "failing_tool"


def test_resolve_evidence_repo_map() -> None:
    p = Proposal(
        op="add",
        kind="repo_map",
        entry_id="rm1",
        content="map",
        evidence_refs=["src", "lib"],
    )
    assert resolve_evidence(p) == {"dirs": ["src", "lib"]}


def test_resolve_evidence_rule() -> None:
    p = Proposal(op="add", kind="rule", entry_id="r1", content="rule", evidence_refs=["x"])
    assert resolve_evidence(p) == {"refs": ["x"]}


def _day(offset: int) -> str:
    return (datetime.now(UTC).date() - timedelta(days=offset)).isoformat()


def _session_with_reread(conn, run_id: str, day: str, path: str, reads: int) -> None:
    conn.execute(
        """
        INSERT INTO runs (run_id, source, external_id, started_at, ended_at,
            status, total_cost, total_input_tokens, total_output_tokens, has_cost)
        VALUES (?, 'claude-code', ?, ?, ?, 'completed', 0, 100, 50, 1)
        """,
        (run_id, run_id, f"{day}T10:00:00Z", f"{day}T10:05:00Z"),
    )
    for seq in range(1, reads + 1):
        conn.execute(
            """
            INSERT INTO events (run_id, seq, type, path_rel, tool_norm_name)
            VALUES (?, ?, 'tool_call', ?, 'read')
            """,
            (run_id, seq, path),
        )


def test_reflector_evidence_measures_file_guide(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        conn = ledger.connection
        _session_with_reread(conn, "b1", _day(3), "src/main.py", 8)
        _session_with_reread(conn, "b2", _day(2), "src/main.py", 7)
        conn.commit()
    finally:
        ledger.close()

    proposal = Proposal(
        op="add",
        kind="file_guide",
        entry_id="fg_main",
        content="`src/main.py`: main entry",
        evidence_refs=["src/main.py"],
    )
    evidence = resolve_evidence(proposal)
    assert evidence == {"path": "src/main.py"}

    record = ProposalRecord(
        op="add",
        entry=Entry(kind="file_guide", entry_id="fg_main", content="`src/main.py`: main entry"),
        evidence=evidence,
        source="reflector:claude",
    )
    result = apply_proposals(root, [record], force=True)
    assert result.applied == 1

    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        conn = ledger.connection
        baseline = conn.execute(
            "SELECT baseline_metric FROM optimizations WHERE block_key='fg_main'"
        ).fetchone()["baseline_metric"]
        assert baseline == 15.0

        for i in range(5):
            _session_with_reread(conn, f"p{i}", _day(0), "src/main.py", 1)
        conn.commit()

        verdicts = compute_outcomes(ledger)
        assert len(verdicts) == 1
        assert verdicts[0].verdict == "improved"
        assert verdicts[0].outcome < baseline
    finally:
        ledger.close()


def _session_with_failure(conn, run_id: str, day: str, tool_name: str) -> None:
    conn.execute(
        """
        INSERT INTO runs (run_id, source, external_id, started_at, ended_at,
            status, total_cost, total_input_tokens, total_output_tokens, has_cost)
        VALUES (?, 'claude-code', ?, ?, ?, 'completed', 0, 100, 50, 1)
        """,
        (run_id, run_id, f"{day}T10:00:00Z", f"{day}T10:05:00Z"),
    )
    conn.execute(
        """
        INSERT INTO events (run_id, seq, type, tool_name, tool_is_error)
        VALUES (?, 1, 'tool_result', ?, 1)
        """,
        (run_id, tool_name),
    )


def test_reflector_evidence_measures_command_fix(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        conn = ledger.connection
        for i in range(4):
            _session_with_failure(conn, f"b{i}", _day(4 + i), "bad_cmd")
        conn.commit()
    finally:
        ledger.close()

    proposal = Proposal(
        op="add",
        kind="command_fix",
        entry_id="cf_bad",
        content="Use good_cmd instead of bad_cmd",
        evidence_refs=["bad_cmd"],
    )
    evidence = resolve_evidence(proposal)
    assert evidence["bad"] == "bad_cmd"

    record = ProposalRecord(
        op="add",
        entry=Entry(kind="command_fix", entry_id="cf_bad", content="Use good_cmd instead."),
        evidence=evidence,
        source="reflector:codex",
    )
    result = apply_proposals(root, [record], force=True)
    assert result.applied == 1

    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        conn = ledger.connection
        baseline = conn.execute(
            "SELECT baseline_metric FROM optimizations WHERE block_key='cf_bad'"
        ).fetchone()["baseline_metric"]
        assert baseline >= 4.0

        for i in range(5):
            _session_with_failure(conn, f"p{i}", _day(0), "bad_cmd")
        conn.commit()

        verdicts = compute_outcomes(ledger)
        assert len(verdicts) == 1
        assert verdicts[0].verdict == "worsened"
    finally:
        ledger.close()


def test_classify_edge_cases() -> None:
    assert classify(0, 0) == "neutral"
    assert classify(0, 3) == "worsened"
    assert classify(10, 7) == "improved"
    # ±10% band: 8 < 10*0.9 == 9 → improved (was neutral under the old 30% band).
    assert classify(10, 8) == "improved"
    assert classify(10, 9.5) == "neutral"
    assert classify(10, 11) == "neutral"
    assert classify(10, 12) == "worsened"
