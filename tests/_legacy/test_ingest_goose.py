"""Goose ingest smoke test."""

from __future__ import annotations

from pathlib import Path

from cairn.ingest.parsers.goose import parse_goose_jsonl
from cairn.ingest.writer import CaptureWriter


def test_ingest_goose_session(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "agent_jsonl_mini.jsonl"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_goose_jsonl(fixture, repo_root=root)
    assert parsed is not None
    assert parsed.source == "goose"
    assert parsed.usage.usage.input_tokens == 12

    writer = CaptureWriter(root)
    try:
        result = writer.ingest_agent_session(parsed)
        assert result.inserted
        row = writer.connection.execute(
            "SELECT source FROM runs WHERE run_id = ?", (result.run_id,)
        ).fetchone()
        assert row["source"] == "goose"
        # tool_call structure preserved
        events = writer.load_events(result.run_id)
        assert any(e["type"] == "tool_call" for e in events)
    finally:
        writer.close()
