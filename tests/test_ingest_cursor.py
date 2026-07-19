"""Cursor ingest adapter tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from server.ingest.adapters import cursor
from server.ingest.adapters.cursor_adapter import CursorAdapter
from server.ingest.adapters.cursor_models import ParsedCursorSession
from server.ingest.adapters.cursor_transcript import parse_transcript_file
from server.ingest.adapters.cursor_vscdb import parse_cursor_vscdb
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


def test_cursor_fixture_parses(tmp_path: Path) -> None:
    adapter = CursorAdapter(tmp_path, new_ulid())
    parsed = adapter.parse_path(FIXTURES / "cursor_mini.jsonl")
    assert parsed is not None
    assert parsed.events


def test_cursor_turn_ended_success_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "turn.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "role": "user",
                        "message": {
                            "content": [{"type": "text", "text": "<user_query>\nhi\n</user_query>"}]
                        },
                    }
                ),
                json.dumps(
                    {
                        "role": "assistant",
                        "message": {"content": [{"type": "text", "text": "hello"}]},
                    }
                ),
                json.dumps({"type": "turn_ended", "status": "success"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    parsed = parse_transcript_file(path, repo_root=tmp_path)
    assert parsed is not None
    assert [e["type"] for e in parsed.events] == ["user_prompt", "assistant_message"]


def test_cursor_turn_ended_error_is_recorded(tmp_path: Path) -> None:
    path = tmp_path / "turn-err.jsonl"
    path.write_text(
        json.dumps({"type": "turn_ended", "status": "error", "error": "tool failed"}) + "\n",
        encoding="utf-8",
    )
    parsed = parse_transcript_file(path, repo_root=tmp_path, external_id="sess-err")
    assert parsed is not None
    assert parsed.events[0]["type"] == "error"
    assert parsed.events[0]["message"] == "tool failed"


def test_cursor_parse_is_deterministic(tmp_path: Path) -> None:
    adapter = CursorAdapter(tmp_path, new_ulid())
    path = FIXTURES / "cursor_mini.jsonl"
    first = adapter.parse_path(path)
    second = adapter.parse_path(path)
    assert first is not None and second is not None
    assert first.external_id == second.external_id
    assert [e.get("event_id") for e in first.events] == [e.get("event_id") for e in second.events]


def test_cursor_facade_preserves_stage_import_identity() -> None:
    assert cursor.ParsedCursorSession is ParsedCursorSession
    assert cursor.parse_cursor_vscdb is parse_cursor_vscdb
    assert cursor.parse_transcript_file is parse_transcript_file


def test_cursor_vscdb_stage_decodes_bubbles_read_only(tmp_path: Path) -> None:
    database = tmp_path / "state.vscdb"
    conn = sqlite3.connect(database)
    conn.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
    rows = [
        (
            "composerData:composer-1",
            {
                "createdAt": 1_767_225_600_000,
                "lastUpdatedAt": 1_767_225_660_000,
                "source": str(tmp_path),
                "fullConversationHeadersOnly": ["user-1", "assistant-1"],
                "usageData": {"default": {"costInCents": 12}},
            },
        ),
        (
            "bubbleId:composer-1:user-1",
            {
                "type": 1,
                "text": "<user_query>Fix the parser</user_query>",
                "tokenCount": {"inputTokens": 20},
            },
        ),
        (
            "bubbleId:composer-1:assistant-1",
            {
                "type": 2,
                "text": "I will inspect it.",
                "tokenCount": {"outputTokens": 10},
            },
        ),
    ]
    conn.executemany(
        "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
        [(key, json.dumps(value)) for key, value in rows],
    )
    conn.commit()
    conn.close()

    before = database.read_bytes()
    sessions = parse_cursor_vscdb(database, repo_root=tmp_path)

    assert database.read_bytes() == before
    assert len(sessions) == 1
    session = sessions[0]
    assert session.external_id == "composer-1"
    assert session.usage.usage.input_tokens == 20
    assert session.usage.usage.output_tokens == 10
    assert session.usage.usage.cost == 0.12
    assert [event["type"] for event in session.events] == [
        "user_prompt",
        "assistant_message",
    ]
