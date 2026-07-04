"""OpenClaw ingest tests."""

from __future__ import annotations

from pathlib import Path

from cairn.ingest.parsers.openclaw import parse_openclaw_file
from cairn.ingest.writer import CaptureWriter


def test_ingest_openclaw_session(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "openclaw_mini.jsonl"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_openclaw_file(fixture, repo_root=root)
    assert parsed is not None
    assert len(parsed.events) >= 4
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_openclaw_session(parsed)
        assert result.inserted
    finally:
        writer.close()
