"""Live ``state.vscdb`` watcher tests (§2.7G)."""

from __future__ import annotations

import time
from pathlib import Path

from cairn.ingest.watch import WATCH_EXTRA_PATHS, VscdbWatcher, watched_vscdb_paths


def test_watched_vscdb_paths_includes_existing(tmp_path: Path, monkeypatch) -> None:
    rel = WATCH_EXTRA_PATHS[1]  # linux path
    vscdb = tmp_path / rel
    vscdb.parent.mkdir(parents=True)
    vscdb.write_text("", encoding="utf-8")
    monkeypatch.setattr("cairn.ingest.watch.Path.home", lambda: tmp_path)
    paths = watched_vscdb_paths()
    assert any(p.name == "state.vscdb" for p in paths)


def test_vscdb_watcher_invokes_handler_on_mtime_change(tmp_path: Path) -> None:
    vscdb = tmp_path / "state.vscdb"
    vscdb.write_text("v1", encoding="utf-8")
    calls: list[int] = []

    watcher = VscdbWatcher(lambda: calls.append(1), paths=[vscdb], poll_s=0.05, debounce_s=0.15)
    watcher.start()
    try:
        time.sleep(0.1)
        vscdb.write_text("v2", encoding="utf-8")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if calls:
                break
            time.sleep(0.05)
        assert calls, "expected vscdb mtime change to trigger handler"
    finally:
        watcher.stop()
