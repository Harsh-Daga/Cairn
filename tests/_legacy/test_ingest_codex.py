"""Codex ingest smoke test."""

from __future__ import annotations

from pathlib import Path

from cairn.ingest.parsers.codex import parse_rollout_file
from cairn.ingest.writer import CaptureWriter


def test_ingest_codex_session(tmp_path: Path) -> None:
    fixtures = list((Path(__file__).parent / "fixtures" / "ingest").glob("codex*.jsonl"))
    if not fixtures:
        return
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_rollout_file(fixtures[0], repo_root=root)
    if parsed is None:
        return
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_codex_session(parsed)
        row = writer.connection.execute(
            "SELECT has_cost FROM runs WHERE run_id = ?", (result.run_id,)
        ).fetchone()
        assert row["has_cost"] == 1
    finally:
        writer.close()


def test_codex_rejects_non_session_meta(tmp_path: Path) -> None:
    """§2.3 validation: only parse files whose first line is session_meta."""
    bad = tmp_path / "not_codex.jsonl"
    bad.write_text(
        '{"timestamp":"2026-06-01T10:00:00Z","type":"event_msg","payload":{"type":"task_started"}}\n',
        encoding="utf-8",
    )
    assert parse_rollout_file(bad, repo_root=tmp_path) is None


def test_codex_per_turn_delta_context_window_and_rate_limits(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "codex_tokens.jsonl"
    parsed = parse_rollout_file(fixture, repo_root=tmp_path)
    assert parsed is not None

    # context window captured from model_context_window
    assert parsed.context_window == 200000

    # rate_limits.primary captured
    assert parsed.rate_limit_used_pct == 55.0  # last wins
    assert parsed.rate_limit_window_min == 300
    assert parsed.rate_limit_resets_at == "2026-06-01T10:05:00Z"
    assert parsed.plan_type == "pro"

    # per-turn delta: usage accumulates each token_count's last_token_usage.
    # Final task_complete usage adds input=1400, output=350 on top.
    assert parsed.usage.usage.input_tokens >= 1200 + 1400
    assert parsed.usage.usage.output_tokens >= 300 + 350

    # token_count events carry context_tokens_after (per-turn context fill)
    tok_events = [e for e in parsed.events if e["type"] == "token_count"]
    assert len(tok_events) == 2
    assert tok_events[0]["context_tokens_after"] == 2300
    assert tok_events[1]["context_tokens_after"] == 2650

    # persists to ledger
    root = tmp_path / "proj"
    root.mkdir()
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_codex_session(parsed)
        row = writer.connection.execute(
            "SELECT context_window, rate_limit_used_pct, rate_limit_window_min, plan_type "
            "FROM runs WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
        assert int(row["context_window"]) == 200000
        assert float(row["rate_limit_used_pct"]) == 55.0
        assert int(row["rate_limit_window_min"]) == 300
        assert row["plan_type"] == "pro"
    finally:
        writer.close()
