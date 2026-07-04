"""OpenCode ingest smoke test (§2.4)."""

from __future__ import annotations

from pathlib import Path

from cairn.ingest.parsers.opencode import parse_opencode_jsonl
from cairn.ingest.writer import CaptureWriter


def test_ingest_opencode_session(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "agent_jsonl_mini.jsonl"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_opencode_jsonl(fixture, repo_root=root)
    assert parsed is not None
    assert parsed.source == "opencode"
    # usage extracted from the assistant message's usage block
    assert parsed.usage.usage.input_tokens == 12
    assert parsed.usage.usage.output_tokens == 6
    assert parsed.started_at == "2026-06-01T10:00:00Z"

    writer = CaptureWriter(root)
    try:
        result = writer.ingest_agent_session(parsed)
        assert result.inserted
        assert result.event_count > 0
        row = writer.connection.execute(
            "SELECT source FROM runs WHERE run_id = ?", (result.run_id,)
        ).fetchone()
        assert row["source"] == "opencode"
    finally:
        writer.close()
