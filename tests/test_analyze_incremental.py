"""Incremental analyzer scheduler tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from server.analyze.registry import build_views
from server.analyze.tail import fit_gpd_exceedances
from server.analyze.views import ViewScheduler
from server.api.sse import EventBus
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.pipeline import IngestPipeline
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.views import ViewStateRepo
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


def test_scheduler_runs_once_per_trace(
    pipeline_bundle: tuple[IngestPipeline, Database, str],
) -> None:
    pipeline, db, ws_id = pipeline_bundle
    adapter = ClaudeCodeAdapter(pipeline.workspace_root, ws_id)
    paths = [
        FIXTURES / "wasteful_session.jsonl",
        FIXTURES / "claude_code_mini.jsonl",
        FIXTURES / "claude_estimation.jsonl",
    ]
    for path in paths:
        pipeline._path_adapter[path.resolve()] = (adapter, "claude_code")
        pipeline.ingest_path(path)

    usage_rows = ViewStateRepo.list_by_view(db.reader, "usage")
    waste_rows = ViewStateRepo.list_by_view(db.reader, "waste")
    assert len(usage_rows) == 3
    assert len(waste_rows) == 3


def test_scheduler_skips_unchanged(pipeline_bundle: tuple[IngestPipeline, Database, str]) -> None:
    pipeline, db, ws_id = pipeline_bundle
    adapter = ClaudeCodeAdapter(pipeline.workspace_root, ws_id)
    path = FIXTURES / "wasteful_session.jsonl"
    pipeline._path_adapter[path.resolve()] = (adapter, "claude_code")
    result = pipeline.ingest_path(path)
    assert result is not None

    scheduler = ViewScheduler(db.reader, build_views(ws_id))
    dirty = [f"usage:{result.trace_id}"]
    first = scheduler.run(dirty)
    assert first == []
    assert scheduler.compute_calls == 0


def test_gpd_recovers_shape_on_synthetic_pareto() -> None:
    rng = np.random.default_rng(0)
    exceedances = rng.exponential(2.0, size=120)
    xi, sigma = fit_gpd_exceedances(exceedances)
    assert sigma > 0
    assert abs(xi) < 0.15
    assert abs(sigma - 2.0) < 0.6
