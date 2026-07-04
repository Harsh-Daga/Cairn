"""Gemini CLI ingest tests."""

from __future__ import annotations

from pathlib import Path

from cairn.ingest.parsers.gemini_cli import parse_gemini_file
from cairn.ingest.writer import CaptureWriter


def test_ingest_gemini_session(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "gemini_mini.jsonl"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_gemini_file(fixture, repo_root=root)
    assert parsed is not None
    assert len(parsed.events) >= 4
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_gemini_session(parsed)
        assert result.inserted
    finally:
        writer.close()
