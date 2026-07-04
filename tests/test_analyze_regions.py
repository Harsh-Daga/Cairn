"""Context-region incremental analyzer tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from server.api.sse import EventBus
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.pipeline import IngestPipeline
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.context_regions import ContextRegionRepo
from server.store.repos.spans import SpanRepo
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
    bus = EventBus()
    pipeline = IngestPipeline(db, ws_id, root, bus)
    return pipeline, db, ws_id


def test_regions_view_writes_context_regions(
    pipeline_bundle: tuple[IngestPipeline, Database, str],
) -> None:
    pipeline, db, ws_id = pipeline_bundle
    adapter = ClaudeCodeAdapter(pipeline.workspace_root, ws_id)
    path = FIXTURES / "wasteful_session.jsonl"
    pipeline._path_adapter[path.resolve()] = (adapter, "claude_code")
    result = pipeline.ingest_path(path)
    assert result is not None

    rows = ContextRegionRepo.list_by_trace(db.reader, result.trace_id)
    assert rows
    region_names = {row.region for row in rows}
    assert "assistant_history" not in region_names
    assert "tool_result" in region_names
    assert "retrieved" in region_names
    assert any(row.cost > 0 for row in rows)

    span_ids = {span.span_id for span in SpanRepo.list_by_trace(db.reader, result.trace_id)}
    assert span_ids
    assert {row.span_id for row in rows}.issubset(span_ids)
