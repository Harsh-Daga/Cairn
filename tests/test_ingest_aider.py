"""Aider ingest smoke test."""

from __future__ import annotations

from pathlib import Path

from cairn.ingest.parsers.aider import parse_aider_jsonl
from cairn.ingest.writer import CaptureWriter


def test_ingest_aider_session(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "agent_jsonl_mini.jsonl"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_aider_jsonl(fixture, repo_root=root)
    assert parsed is not None
    assert parsed.source == "aider"
    assert parsed.usage.usage.output_tokens == 6

    writer = CaptureWriter(root)
    try:
        result = writer.ingest_agent_session(parsed)
        assert result.inserted
        row = writer.connection.execute(
            "SELECT source FROM runs WHERE run_id = ?", (result.run_id,)
        ).fetchone()
        assert row["source"] == "aider"
    finally:
        writer.close()
