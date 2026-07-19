"""OpenCode SQLite store ingest tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from server.api.action_handlers import WorkspaceScanParams
from server.ingest.adapters.generic_jsonl_adapter import OpenCodeAdapter
from server.ingest.adapters.opencode_db import (
    _ensure_session_stub,
    _stub_path_for_session,
    discover_opencode_db_sessions,
    parse_opencode_db_session,
)
from server.util.ids import new_ulid


def _seed_opencode_db(db_path: Path, *, directory: str) -> str:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE session (
          id TEXT PRIMARY KEY,
          project_id TEXT,
          directory TEXT,
          title TEXT,
          model TEXT,
          time_created INTEGER,
          time_updated INTEGER,
          cost REAL,
          tokens_input INTEGER,
          tokens_output INTEGER,
          tokens_reasoning INTEGER,
          tokens_cache_read INTEGER,
          tokens_cache_write INTEGER,
          agent TEXT
        );
        CREATE TABLE message (
          id TEXT PRIMARY KEY,
          session_id TEXT,
          time_created INTEGER,
          time_updated INTEGER,
          data TEXT
        );
        CREATE TABLE part (
          id TEXT PRIMARY KEY,
          message_id TEXT,
          session_id TEXT,
          time_created INTEGER,
          time_updated INTEGER,
          data TEXT
        );
        """
    )
    session_id = "ses_test_opencode_1"
    conn.execute(
        """
        INSERT INTO session (
          id, project_id, directory, title, model, time_created, time_updated,
          cost, tokens_input, tokens_output, tokens_reasoning,
          tokens_cache_read, tokens_cache_write, agent
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            "proj",
            directory,
            "test",
            json.dumps({"providerID": "openai", "modelID": "gpt-test"}),
            1_700_000_000_000,
            1_700_000_001_000,
            0.12,
            100,
            40,
            0,
            10,
            0,
            "build",
        ),
    )
    conn.execute(
        "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?,?,?,?,?)",
        (
            "msg_user",
            session_id,
            1_700_000_000_100,
            1_700_000_000_100,
            json.dumps({"role": "user"}),
        ),
    )
    conn.execute(
        (
            "INSERT INTO part (id, message_id, session_id, time_created, "
            "time_updated, data) VALUES (?,?,?,?,?,?)"
        ),
        (
            "prt_user",
            "msg_user",
            session_id,
            1_700_000_000_100,
            1_700_000_000_100,
            json.dumps({"type": "text", "text": "edit the file"}),
        ),
    )
    conn.execute(
        "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?,?,?,?,?)",
        (
            "msg_asst",
            session_id,
            1_700_000_000_200,
            1_700_000_000_200,
            json.dumps({"role": "assistant", "modelID": "gpt-test", "providerID": "openai"}),
        ),
    )
    conn.execute(
        (
            "INSERT INTO part (id, message_id, session_id, time_created, "
            "time_updated, data) VALUES (?,?,?,?,?,?)"
        ),
        (
            "prt_text",
            "msg_asst",
            session_id,
            1_700_000_000_200,
            1_700_000_000_200,
            json.dumps({"type": "text", "text": "editing"}),
        ),
    )
    conn.execute(
        (
            "INSERT INTO part (id, message_id, session_id, time_created, "
            "time_updated, data) VALUES (?,?,?,?,?,?)"
        ),
        (
            "prt_tool",
            "msg_asst",
            session_id,
            1_700_000_000_300,
            1_700_000_000_300,
            json.dumps(
                {
                    "type": "tool",
                    "tool": "edit",
                    "callID": "call_1",
                    "state": {
                        "status": "completed",
                        "input": {
                            "filePath": f"{directory}/app.py",
                            "oldString": "a",
                            "newString": "b",
                        },
                        "output": "ok",
                    },
                }
            ),
        ),
    )
    conn.commit()
    conn.close()
    return session_id


def test_parse_opencode_db_session(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    db_path = tmp_path / "opencode.db"
    session_id = _seed_opencode_db(db_path, directory=str(project))
    monkeypatch.setattr(
        "server.ingest.adapters.opencode_db.opencode_db_path",
        lambda: db_path,
    )
    monkeypatch.setattr(
        "server.ingest.adapters.opencode_db.opencode_stream_stub_root",
        lambda: tmp_path / "stubs",
    )

    stubs = discover_opencode_db_sessions(project)
    assert len(stubs) == 1
    adapter = OpenCodeAdapter(project, new_ulid())
    parsed = adapter.parse_path(stubs[0])
    assert parsed is not None
    assert parsed.external_id == session_id
    assert parsed.usage.input_tokens == 100
    assert parsed.usage.output_tokens == 40
    assert any(e.get("type") == "user_prompt" for e in parsed.events)
    assert [t.name for t in parsed.tool_calls] == ["edit"]

    direct = parse_opencode_db_session(db_path, session_id, repo_root=project)
    assert direct is not None
    assert len(direct.tool_calls) == 1


def test_opencode_stub_rejects_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "server.ingest.adapters.opencode_db.opencode_stream_stub_root",
        lambda: tmp_path / "stubs",
    )
    escaped = _stub_path_for_session("../evil")
    assert escaped is not None
    assert escaped.parent == (tmp_path / "stubs").resolve()
    assert ".." not in escaped.name

    stub = _ensure_session_stub(
        session_id="../evil",
        db=tmp_path / "opencode.db",
        directory=str(tmp_path),
        title="x",
        mtime_ms=1_700_000_000_000,
    )
    assert stub is not None
    assert stub.is_relative_to((tmp_path / "stubs").resolve())


def test_workspace_scan_force_defaults_false() -> None:
    assert WorkspaceScanParams().force is False
