"""Replay checkpoint interpolation tests."""

from __future__ import annotations

import pytest

from server.api.payloads import build_replay_checkpoints
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid


@pytest.fixture
def db_with_spans(tmp_path):
    database = Database(tmp_path / "cairn.db")
    ws_id = new_ulid()
    WorkspaceRepo.create(
        database.reader,
        Workspace(
            workspace_id=ws_id,
            root_path=str(tmp_path),
            name="t",
            created_at="2026-01-01",
        ),
    )
    trace_id = new_ulid()
    database.reader.execute(
        "INSERT INTO traces (trace_id, workspace_id, source, started_at, status, span_count) "
        "VALUES (?, ?, 'claude_code', '2026-01-01', 'completed', 100)",
        (trace_id, ws_id),
    )
    for i in range(1, 101):
        database.reader.execute(
            "INSERT INTO spans "
            "(span_id, trace_id, seq, kind, name, status, input_tokens, output_tokens) "
            "VALUES (?, ?, ?, 'user_msg', 'turn', 'ok', 10, 5)",
            (new_ulid(), trace_id, i),
        )
    database.reader.commit()
    return database, trace_id


def test_replay_checkpoints_step_and_coverage(db_with_spans) -> None:
    db, trace_id = db_with_spans
    resp = build_replay_checkpoints(db.reader, trace_id)
    assert resp is not None
    assert resp.max_seq == 100
    assert resp.step == 3  # ceil(100/40)
    assert resp.checkpoints is not None
    assert resp.checkpoints[-1].seq == 100
    assert len(resp.checkpoints[-1].spans) == 100
