"""Difficulty analyzer tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from server.analyze.difficulty import estimate_difficulty
from server.api.sse import EventBus
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.pipeline import IngestPipeline
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.traces import TraceRepo
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


def test_estimate_difficulty_increases_for_harder_work() -> None:
    trivial = estimate_difficulty(
        {"total_input_tokens": 50, "total_output_tokens": 20},
        [{"type": "user_prompt", "text_inline": "fix typo"}],
    )
    hard = estimate_difficulty(
        {"total_input_tokens": 40_000, "total_output_tokens": 20_000},
        [
            {
                "type": "user_prompt",
                "text_inline": "migrate pyproject.toml and docker kubernetes setup " * 15,
            },
            {"type": "tool_call", "tool_norm_name": "edit", "path_rel": "src/a/main.py"},
            {"type": "tool_call", "tool_norm_name": "edit", "path_rel": "src/b/util.py"},
            {"type": "tool_call", "tool_norm_name": "read", "path_rel": "src/c/data.py"},
        ],
    )
    assert trivial.difficulty < hard.difficulty


def test_difficulty_view_updates_trace(
    pipeline_bundle: tuple[IngestPipeline, Database, str],
) -> None:
    pipeline, db, ws_id = pipeline_bundle
    adapter = ClaudeCodeAdapter(pipeline.workspace_root, ws_id)
    path = FIXTURES / "wasteful_session.jsonl"
    pipeline._path_adapter[path.resolve()] = (adapter, "claude_code")
    result = pipeline.ingest_path(path)
    assert result is not None

    trace = TraceRepo.get(db.reader, result.trace_id)
    assert trace is not None
    assert trace.difficulty is not None
    assert trace.difficulty_bucket in {"trivial", "standard", "hard", "epic"}
