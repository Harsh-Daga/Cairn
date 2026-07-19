"""Collection mode Manual / Efficient / Live honesty coverage."""

from __future__ import annotations

from pathlib import Path

from server.api.sse import EventBus
from server.ingest.collection import resolve_collection_runtime
from server.ingest.pipeline import IngestPipeline
from server.store.db import Database
from server.util.ids import new_ulid
from server.util.private_files import write_private_text


def test_runtime_modes_match_contracts() -> None:
    manual = resolve_collection_runtime("manual")
    assert manual.auto_sync_enabled is False
    assert manual.watcher_enabled is False
    efficient = resolve_collection_runtime("efficient")
    assert efficient.watcher_enabled and efficient.refresh_enabled
    live = resolve_collection_runtime("live")
    assert live.poll_interval_sec < efficient.poll_interval_sec
    assert "SSE" in live.limitation or "Live updates" in live.limitation


def test_manual_mode_starts_without_background_threads(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    cairn = root / ".cairn"
    cairn.mkdir()
    write_private_text(cairn / "config.toml", '[collection]\nmode = "manual"\n')
    db = Database(cairn / "cairn.db")
    ws_id = new_ulid()
    db.write(
        lambda conn: conn.execute(
            "INSERT INTO workspaces (workspace_id, root_path, name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (ws_id, str(root), "c", "2026-07-01T00:00:00Z"),
        )
    )
    bus = EventBus()
    pipeline = IngestPipeline(db, ws_id, root, bus)
    status = pipeline.apply_collection_mode("manual")
    assert status["mode"] == "manual"
    assert status["auto_sync"]["enabled"] is False
    assert status["auto_sync"]["running"] is False
    assert pipeline._worker is None
    assert pipeline._refresh is None
    # Sync now still works.
    report = pipeline.sync_all()
    assert report.scanned >= 0
    pipeline.stop()
    db.close()
