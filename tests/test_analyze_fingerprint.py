"""Fingerprint analyzer tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from server.analyze.fingerprint import VECTOR_DIM, FingerprintView
from server.api.sse import EventBus
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.pipeline import IngestPipeline
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.fingerprints import FingerprintRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


@pytest.fixture
def ingested_trace(tmp_path: Path) -> tuple[Database, str]:
    root = tmp_path / "proj"
    root.mkdir()
    db = Database(tmp_path / "cairn.db")
    workspace_id = new_ulid()
    WorkspaceRepo.create(
        db.reader,
        Workspace(
            workspace_id=workspace_id,
            root_path=str(root),
            name="proj",
            created_at="2026-01-01T00:00:00Z",
        ),
    )
    db.reader.commit()
    pipeline = IngestPipeline(db, workspace_id, root, EventBus())
    adapter = ClaudeCodeAdapter(root, workspace_id)
    fixture = FIXTURES / "wasteful_session.jsonl"
    pipeline._path_adapter[fixture.resolve()] = (adapter, "claude_code")
    result = pipeline.ingest_path(fixture)
    assert result is not None
    return db, result.trace_id


def test_fingerprint_vector_non_empty(ingested_trace: tuple[Database, str]) -> None:
    db, trace_id = ingested_trace

    def _compute(conn: sqlite3.Connection) -> tuple[int, bool]:
        view = FingerprintView()
        view.compute(conn, trace_id)
        row = FingerprintRepo.get(conn, trace_id)
        assert row is not None
        return len(row.vector), any(value > 0 for value in row.vector)

    vector_len, has_signal = db.write(_compute)
    assert vector_len == VECTOR_DIM
    assert has_signal
