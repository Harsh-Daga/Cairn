"""`cairn show` text waterfall tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from server.api.bootstrap import bootstrap_runtime
from server.api.show import render_waterfall
from server.config import Settings
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.pipeline import IngestPipeline
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


def _seed_trace(root: Path) -> str:
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
    return trace_id


def test_render_waterfall_has_tree_and_columns(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    trace_id = _seed_trace(root)
    runtime = bootstrap_runtime(Settings(workspace_root=root))
    text = render_waterfall(runtime.database.reader, trace_id)
    assert text is not None
    assert "cost=$" in text
    assert "in" in text and "out" in text
    assert "user_msg" in text or "tool_call" in text or "assistant_msg" in text


def test_cli_show_prints_waterfall(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    trace_id = _seed_trace(root)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "server.cli",
            "show",
            trace_id,
            "--workspace",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert trace_id in result.stdout or "cost=$" in result.stdout
