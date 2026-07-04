"""Data quality + estimation provenance tests (Phase 0)."""

from __future__ import annotations

from pathlib import Path

from cairn.ingest import tokenize
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.parsers.codex import parse_rollout_file
from cairn.ingest.usage import estimate_claude_turn
from cairn.ingest.writer import CaptureWriter

_FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


def test_estimated_usage_carries_error_pct() -> None:
    usage = estimate_claude_turn(
        {"input_tokens": 2, "output_tokens": 2, "cache_read_input_tokens": 50},
        assistant_text="A longer assistant reply for estimation.",
        user_text="User prompt text here.",
        model="claude-sonnet-4-5",
    )
    assert usage.input_estimated
    assert usage.output_estimated
    assert usage.input_estimation_error_pct is not None
    assert usage.output_estimation_error_pct is not None


def test_fixture_token_measurement_rate(tmp_path: Path) -> None:
    """Bundled fixtures with real usage: >=95% tokens measured."""
    tokenize.reset_calibration()
    root = tmp_path / "proj"
    root.mkdir()
    measured_rates: list[float] = []

    for fixture, ingest_fn in (
        (_FIXTURES / "claude_code_mini.jsonl", "claude"),
        (_FIXTURES / "codex_tokens.jsonl", "codex"),
    ):
        writer = CaptureWriter(root)
        try:
            if ingest_fn == "claude":
                parsed = parse_jsonl_file(fixture, repo_root=root)
                assert parsed is not None
                result = writer.ingest_claude_session(parsed)
            else:
                parsed = parse_rollout_file(fixture, repo_root=root)
                assert parsed is not None
                result = writer.ingest_codex_session(parsed)
            row = writer.connection.execute(
                "SELECT pct_tokens_measured FROM data_quality WHERE run_id = ?",
                (result.run_id,),
            ).fetchone()
            assert row is not None
            if row["pct_tokens_measured"] is not None:
                measured_rates.append(float(row["pct_tokens_measured"]))
        finally:
            writer.close()

    assert measured_rates
    assert min(measured_rates) >= 95.0
