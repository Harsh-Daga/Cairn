"""Phase 3 pipeline e2e tests."""

from __future__ import annotations

import json
import queue
import shutil
import threading
import time
from pathlib import Path

import pytest

from server.api.sse import EventBus
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.pipeline import IngestPipeline, PipelineReport
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.traces import TraceRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


@pytest.fixture
def workspace_bundle(tmp_path: Path) -> tuple[Database, str, Path]:
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
    return db, ws_id, root


def _collect_sse(bus: EventBus) -> tuple[queue.Queue[object], threading.Thread]:
    received: queue.Queue[object] = queue.Queue()

    def _reader() -> None:
        client_id, iterator = bus.subscribe()
        try:
            for event in iterator:
                received.put(event)
                if received.qsize() >= 2:
                    break
        finally:
            bus.unsubscribe(client_id)

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    return received, thread


def test_pipeline_ingest_trace_and_sse(workspace_bundle: tuple[Database, str, Path]) -> None:
    db, ws_id, root = workspace_bundle
    bus = EventBus()
    received, _thread = _collect_sse(bus)

    fixture = FIXTURES / "wasteful_session.jsonl"
    pipeline = IngestPipeline(db, ws_id, root, bus)
    adapter = ClaudeCodeAdapter(root, ws_id)
    pipeline._path_adapter[fixture.resolve()] = (adapter, "claude_code")

    result = pipeline.ingest_path(fixture)
    assert result is not None
    assert result.inserted
    assert result.span_count > 0

    trace = TraceRepo.get(db.reader, result.trace_id)
    assert trace is not None
    assert trace.input_tokens > 0
    health = db.reader.execute(
        "SELECT attempts, fully_parsed, degraded, skipped FROM adapter_parse_health"
    ).fetchone()
    assert dict(health) == {"attempts": 1, "fully_parsed": 1, "degraded": 0, "skipped": 0}

    event = received.get(timeout=2)
    assert event.event == "trace-updated"
    payload = event.data
    assert payload["trace_id"] == result.trace_id


def test_watcher_detects_appended_log(workspace_bundle: tuple[Database, str, Path]) -> None:
    db, ws_id, root = workspace_bundle
    bus = EventBus()
    log_path = root / "live_session.jsonl"
    shutil.copy(FIXTURES / "claude_code_mini.jsonl", log_path)

    pipeline = IngestPipeline(db, ws_id, root, bus)
    adapter = ClaudeCodeAdapter(root, ws_id)
    pipeline._path_adapter[log_path.resolve()] = (adapter, "claude_code")
    pipeline._watcher.add_path(log_path)
    pipeline._watcher.start()

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "extra line"}]},
                }
            )
            + "\n"
        )

    deadline = time.time() + 3
    result = None
    while time.time() < deadline:
        result = pipeline.ingest_path(log_path)
        if result is not None:
            break
        time.sleep(0.2)
        pipeline._watcher._scan_once()

    pipeline.stop()
    assert result is not None
    assert TraceRepo.get(db.reader, result.trace_id) is not None


def test_start_runs_initial_sync(
    workspace_bundle: tuple[Database, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    db, ws_id, root = workspace_bundle
    pipeline = IngestPipeline(db, ws_id, root, EventBus())
    calls = 0
    synced = threading.Event()

    def fake_sync(source: str | None = None) -> PipelineReport:
        nonlocal calls
        calls += 1
        synced.set()
        return PipelineReport()

    monkeypatch.setattr(pipeline, "sync_all", fake_sync)
    pipeline.start()
    assert synced.wait(timeout=1)
    pipeline.stop()

    assert calls == 1


def test_sync_all_honors_source_filter(
    workspace_bundle: tuple[Database, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    db, ws_id, root = workspace_bundle
    pipeline = IngestPipeline(db, ws_id, root, EventBus())
    adapter = ClaudeCodeAdapter(root, ws_id)
    codex_path = root / "codex.jsonl"
    claude_path = root / "claude.jsonl"
    pipeline._path_adapter = {
        codex_path: (adapter, "codex"),
        claude_path: (adapter, "claude_code"),
    }
    seen: list[tuple[Path, str]] = []

    monkeypatch.setattr(pipeline, "_refresh_path_index", lambda: None)

    def fake_ingest(path: Path, _adapter: object, source: str) -> None:
        seen.append((path, source))

    monkeypatch.setattr(pipeline, "_ingest_path", fake_ingest)
    report = pipeline.sync_all("codex")

    assert report.scanned == 1
    assert report.skipped == 1
    assert seen == [(codex_path, "codex")]


def test_sync_imports_mcp_consultations_idempotently(
    workspace_bundle: tuple[Database, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    db, ws_id, root = workspace_bundle
    trace_id = new_ulid()
    db.reader.execute(
        """INSERT INTO traces (trace_id, workspace_id, source, started_at, status)
           VALUES (?, ?, 'codex', '2026-01-02T00:00:00Z', 'completed')""",
        (trace_id, ws_id),
    )
    db.reader.commit()
    sidecar = root / ".cairn" / "mcp-events.jsonl"
    sidecar.parent.mkdir()
    sidecar.write_text(
        json.dumps(
            {
                "event_id": new_ulid(),
                "trace_id": trace_id,
                "after_seq": 7,
                "tool_name": "cairn_should_i_stop",
                "called_at": "2026-01-02T00:01:00Z",
            }
        )
        + "\n"
        + "not-json\n",
        encoding="utf-8",
    )
    pipeline = IngestPipeline(db, ws_id, root, EventBus())
    monkeypatch.setattr(pipeline, "_refresh_path_index", lambda: None)

    first = pipeline.sync_all()
    second = pipeline.sync_all()

    assert first.mcp_consultations == 1
    assert second.mcp_consultations == 0
    row = db.reader.execute(
        "SELECT trace_id, after_seq, tool_name FROM mcp_consultations"
    ).fetchone()
    assert dict(row) == {
        "trace_id": trace_id,
        "after_seq": 7,
        "tool_name": "cairn_should_i_stop",
    }


def test_sync_all_force_reparses_unchanged_file(
    workspace_bundle: tuple[Database, str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, ws_id, root = workspace_bundle
    source = FIXTURES / "claude_code_mini.jsonl"
    target = root / "stable-claude.jsonl"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    pipeline = IngestPipeline(db, ws_id, root, EventBus())
    monkeypatch.setattr(pipeline, "_refresh_path_index", lambda: None)
    pipeline._path_adapter[target.resolve()] = (ClaudeCodeAdapter(root, ws_id), "claude_code")

    first = pipeline.sync_all()
    second = pipeline.sync_all()
    forced = pipeline.sync_all(force=True)

    assert first.inserted + first.updated == 1
    assert second.skipped == 1
    assert forced.updated == 1
    health = db.reader.execute(
        "SELECT attempts, fully_parsed FROM adapter_parse_health WHERE adapter_id = ?",
        ("claude_code",),
    ).fetchone()
    # force sync rebuilds parse-health from that pass only
    assert health["attempts"] == 1
    assert health["fully_parsed"] == 1


def test_pipeline_marks_unknown_field_spike_as_degraded(
    workspace_bundle: tuple[Database, str, Path],
) -> None:
    db, ws_id, root = workspace_bundle
    source = FIXTURES / "claude_code_mini.jsonl"
    changed = root / "future-claude.jsonl"
    records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    for record in records:
        record["future_schema_field"] = True
    changed.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    pipeline = IngestPipeline(db, ws_id, root, EventBus())
    pipeline._path_adapter[changed.resolve()] = (ClaudeCodeAdapter(root, ws_id), "claude_code")

    assert pipeline.ingest_path(changed) is not None
    row = db.reader.execute("SELECT * FROM adapter_parse_health").fetchone()
    assert row["degraded"] == 1
    assert json.loads(row["recent_unknown_fields_json"])["future_schema_field"] >= 3


def test_pipeline_benign_single_unknown_field_stays_fully_parsed(
    workspace_bundle: tuple[Database, str, Path],
) -> None:
    db, ws_id, root = workspace_bundle
    source = FIXTURES / "claude_code_mini.jsonl"
    changed = root / "one-unknown.jsonl"
    records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    records[0]["future_schema_field"] = True
    changed.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    pipeline = IngestPipeline(db, ws_id, root, EventBus())
    pipeline._path_adapter[changed.resolve()] = (ClaudeCodeAdapter(root, ws_id), "claude_code")

    assert pipeline.ingest_path(changed) is not None
    row = db.reader.execute("SELECT * FROM adapter_parse_health").fetchone()
    assert row["fully_parsed"] == 1
    assert row["degraded"] == 0
    assert json.loads(row["recent_unknown_fields_json"]) == {"future_schema_field": 1}
