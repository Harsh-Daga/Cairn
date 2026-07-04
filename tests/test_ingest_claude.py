"""Claude Code ingest smoke test."""

from __future__ import annotations

from pathlib import Path

from cairn.ingest import tokenize
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter


def test_ingest_claude_session(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "wasteful_session.jsonl"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_jsonl_file(fixture, repo_root=root)
    assert parsed is not None
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_claude_session(parsed)
        assert result.inserted
        assert result.event_count > 0
        row = writer.connection.execute(
            "SELECT has_cost, total_input_tokens FROM runs WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
        assert row["has_cost"] == 1
        assert int(row["total_input_tokens"]) > 0
    finally:
        writer.close()


def test_claude_input_tokens_distrust_and_estimation(tmp_path: Path) -> None:
    """§2.1: input_tokens ≤ 2 is a placeholder → input_estimated=1; output
    estimated from assistant text + thinking blocks."""
    tokenize.reset_calibration()
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "claude_estimation.jsonl"
    user_text = "Fix the auth bug in the login module and explain your reasoning step by step."
    parsed = parse_jsonl_file(fixture, repo_root=tmp_path)
    assert parsed is not None

    assistant_msgs = [e for e in parsed.events if e["type"] == "assistant_message"]
    assert len(assistant_msgs) == 2  # the duplicate req-dup was skipped

    first = assistant_msgs[0]
    assert first["input_estimated"] == 1  # raw input_tokens == 2 → distrust
    est_fresh, _ = tokenize.count_tokens(user_text, model="claude-sonnet-4-5")
    assert first["input_tokens"] >= 150
    assert first["input_tokens"] == 150 + est_fresh
    assert first["output_estimated"] == 1
    # output_tokens must reflect thinking + text, not the raw placeholder (5).
    assert first["output_tokens"] >= 15

    # requestId dedup: the 9999-token duplicate must NOT be absorbed.
    assert parsed.usage.usage.input_tokens < 9999
    assert parsed.usage.usage.output_tokens < 9999

    # thinking blocks are included in the output estimate: the second turn's
    # visible text is just "Done." (~1 tok) but output_tokens is ~50.
    second = assistant_msgs[1]
    assert second["input_estimated"] == 1
    assert second["output_estimated"] == 1
    assert second["output_tokens"] > 30


def test_claude_requestid_dedup_persists(tmp_path: Path) -> None:
    """The dedup must also hold once written to the ledger."""
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "claude_estimation.jsonl"
    parsed = parse_jsonl_file(fixture, repo_root=tmp_path)
    assert parsed is not None
    root = tmp_path / "proj"
    root.mkdir()
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_claude_session(parsed)
        row = writer.connection.execute(
            "SELECT total_input_tokens, total_output_tokens, output_estimated "
            "FROM runs WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
        assert int(row["total_input_tokens"]) < 9999
        assert int(row["total_output_tokens"]) < 9999
        assert int(row["output_estimated"]) == 1
    finally:
        writer.close()


def test_claude_sidechain_agent_lane(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "claude_sidechain_mini.jsonl"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_jsonl_file(fixture, repo_root=root)
    assert parsed is not None
    lanes = {e.get("agent_lane") for e in parsed.events if e.get("agent_lane")}
    assert "main" in lanes
    assert "sidechain" in lanes
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_claude_session(parsed)
        rows = writer.connection.execute(
            "SELECT agent_lane FROM events WHERE run_id = ? AND agent_lane IS NOT NULL",
            (result.run_id,),
        ).fetchall()
        db_lanes = {r["agent_lane"] for r in rows}
        assert "sidechain" in db_lanes
    finally:
        writer.close()
