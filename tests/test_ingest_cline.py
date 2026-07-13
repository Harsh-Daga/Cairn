"""Cline family ingest adapter tests."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.cline_adapter import ClineAdapter
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"
CLINE_TASK = FIXTURES / "cline_mini" / "tasks" / "task-redacted-001" / "ui_messages.json"


def test_cline_fixture_parses(tmp_path: Path) -> None:
    adapter = ClineAdapter(tmp_path, new_ulid())
    parsed = adapter.parse_path(CLINE_TASK)
    assert parsed is not None
    assert parsed.events


def test_cline_parse_is_deterministic(tmp_path: Path) -> None:
    adapter = ClineAdapter(tmp_path, new_ulid())
    first = adapter.parse_path(CLINE_TASK)
    second = adapter.parse_path(CLINE_TASK)
    assert first is not None and second is not None
    assert first.external_id == second.external_id
    assert [e.get("event_id") for e in first.events] == [e.get("event_id") for e in second.events]
