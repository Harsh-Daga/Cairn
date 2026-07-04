"""Cursor ingest adapter tests."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.cursor_adapter import CursorAdapter
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


def test_cursor_fixture_parses(tmp_path: Path) -> None:
    adapter = CursorAdapter(tmp_path, new_ulid())
    parsed = adapter.parse_path(FIXTURES / "cursor_mini.jsonl")
    assert parsed is not None
    assert parsed.events


def test_cursor_parse_is_deterministic(tmp_path: Path) -> None:
    adapter = CursorAdapter(tmp_path, new_ulid())
    path = FIXTURES / "cursor_mini.jsonl"
    first = adapter.parse_path(path)
    second = adapter.parse_path(path)
    assert first is not None and second is not None
    assert first.external_id == second.external_id
    assert [e.get("event_id") for e in first.events] == [
        e.get("event_id") for e in second.events
    ]
