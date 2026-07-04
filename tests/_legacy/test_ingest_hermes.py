"""Hermes ingest smoke test."""

from __future__ import annotations

from pathlib import Path

from cairn.ingest.parsers.hermes import parse_session_file
from cairn.ingest.writer import CaptureWriter


def test_ingest_hermes_session(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "hermes_mini.json"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_session_file(fixture, repo_root=root)
    assert parsed is not None
    assert parsed.external_id == "hermes-sess-redacted"
    assert parsed.started_at == "2026-04-19T09:00:00Z"

    writer = CaptureWriter(root)
    try:
        result = writer.ingest_hermes_session(parsed)
        assert result.inserted
        assert result.event_count > 0
        row = writer.connection.execute(
            "SELECT source, started_at FROM runs WHERE run_id = ?", (result.run_id,)
        ).fetchone()
        assert row["source"] == "hermes"
        assert str(row["started_at"]).startswith("2026-04-19T09:00:00")
    finally:
        writer.close()
