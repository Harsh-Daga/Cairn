"""Shared pytest fixtures for v4 scaffold tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.bootstrap import AppRuntime, bootstrap_runtime
from server.app import create_app
from server.config import Settings
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.pipeline import IngestPipeline
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ingest"


@asynccontextmanager
async def _noop_lifespan(_application: FastAPI) -> AsyncIterator[None]:
    yield


@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture
def api_workspace(tmp_path: Path) -> tuple[Path, str, str]:
    """Create workspace with one ingested trace; return root, workspace_id, trace_id."""
    root = (tmp_path / "proj").resolve()
    root.mkdir()
    db = Database(root / ".cairn" / "cairn.db")
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

    from server.api.sse import EventBus

    bus = EventBus()
    pipeline = IngestPipeline(db, ws_id, root, bus)
    fixture = FIXTURES / "wasteful_session.jsonl"
    pipeline._path_adapter[fixture.resolve()] = (ClaudeCodeAdapter(root, ws_id), "claude_code")
    result = pipeline.ingest_path(fixture)
    assert result is not None
    trace_id = result.trace_id
    db.close()
    return root, ws_id, trace_id


@pytest.fixture
def api_client(api_workspace: tuple[Path, str, str]) -> Generator[TestClient, None, None]:
    root, _ws_id, _trace_id = api_workspace
    settings = Settings(workspace_root=root, static_dir=Settings().static_dir)
    runtime: AppRuntime = bootstrap_runtime(settings)
    application = create_app(settings)
    application.router.lifespan_context = _noop_lifespan
    application.state.runtime = runtime
    application.state.database = runtime.database
    application.state.workspace_id = runtime.workspace_id
    application.state.event_bus = runtime.event_bus
    client = TestClient(application)
    yield client

