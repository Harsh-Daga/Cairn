"""Outcomes incremental analyzer tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from server.api.sse import EventBus
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.pipeline import IngestPipeline
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


@pytest.fixture
def pipeline_bundle(tmp_path: Path) -> tuple[IngestPipeline, Database, str]:
    root = tmp_path / "proj"
    root.mkdir()
    db = Database(tmp_path / "cairn.db")
    ws_id = new_ulid()
    WorkspaceRepo.create(
        db.reader,
        Workspace(
            workspace_id=ws_id,
            root_path=str(root),
            name="proj",
            created_at="2026-01-01T00:00:00Z",
        ),
    )
    db.reader.commit()
    pipeline = IngestPipeline(db, ws_id, root, EventBus())
    return pipeline, db, ws_id


def test_outcome_row_upserted_after_ingest(
    pipeline_bundle: tuple[IngestPipeline, Database, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline, db, ws_id = pipeline_bundle
    adapter = ClaudeCodeAdapter(pipeline.workspace_root, ws_id)
    fixture = FIXTURES / "wasteful_session.jsonl"
    pipeline._path_adapter[fixture.resolve()] = (adapter, "claude_code")
    monkeypatch.setattr("server.analyze.outcomes.test_command_for", lambda _project: None)
    result = pipeline.ingest_path(fixture)
    assert result is not None

    row = OutcomeRepo.get(db.reader, result.trace_id)
    assert row is not None
    assert row.trace_id == result.trace_id
    assert row.build_status == "unknown"
    assert row.captured_at is not None
    assert row.quality_score is not None
