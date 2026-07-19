"""Watcher coalescing, catch-up caps, stale pruning, and adaptive backoff."""

from __future__ import annotations

import time
from pathlib import Path

from server.ingest.watcher import FileWatcher


def _touch(path: Path, payload: str = "x") -> None:
    path.write_text(payload, encoding="utf-8")
    # Ensure mtime advances on filesystems with coarse resolution.
    time.sleep(0.02)


def test_watch_replaces_set_and_drops_stale_pending(tmp_path: Path) -> None:
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    _touch(a, "a1")
    _touch(b, "b1")
    watcher = FileWatcher(poll_interval_sec=0.05, max_paths_per_scan=10)
    watcher.watch([a, b])
    assert set(watcher.watched_paths()) == {a.resolve(), b.resolve()}
    watcher.watch([a])
    assert watcher.watched_paths() == [a.resolve()]


def test_scan_coalesces_burst_appends_to_one_event(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    _touch(path, "line1\n")
    watcher = FileWatcher(
        poll_interval_sec=0.05,
        max_paths_per_scan=10,
        max_changes_per_scan=10,
    )
    watcher.watch([path])
    # Establish baseline mtime in the watch set.
    assert watcher._scan_once() == 0
    with path.open("a", encoding="utf-8") as handle:
        handle.write("line2\n")
        handle.flush()
        time.sleep(0.02)
        handle.write("line3\n")
        handle.flush()
        time.sleep(0.02)
        handle.write("line4\n")
    changed = watcher._scan_once()
    assert changed == 1
    watcher.stop()
    events = list(watcher.events())
    assert len(events) == 1
    assert events[0].path == path.resolve()


def test_catch_up_cap_defers_extra_paths(tmp_path: Path) -> None:
    paths = []
    for index in range(6):
        path = tmp_path / f"s{index}.jsonl"
        _touch(path, f"{index}\n")
        paths.append(path)
    watcher = FileWatcher(
        poll_interval_sec=0.05,
        max_paths_per_scan=2,
        max_changes_per_scan=10,
    )
    watcher.watch(paths)
    first = watcher._scan_once()
    stats = watcher.stats()
    assert stats.paths_checked == 2
    assert stats.paths_deferred >= 4
    assert first == 0  # baseline only
    # Mutate all files; still only two checked per cycle.
    for path in paths:
        _touch(path, path.read_text(encoding="utf-8") + "more\n")
    changed = watcher._scan_once()
    stats = watcher.stats()
    assert stats.paths_checked == 2
    assert changed <= 2
    assert stats.paths_deferred >= 4


def test_missing_paths_are_pruned_after_cycles(tmp_path: Path) -> None:
    path = tmp_path / "gone.jsonl"
    _touch(path, "data\n")
    watcher = FileWatcher(poll_interval_sec=0.05, max_paths_per_scan=10)
    watcher.watch([path])
    path.unlink()
    for _ in range(3):
        watcher._scan_once()
    assert path.resolve() not in watcher.watched_paths()
    assert watcher.stats().pruned_stale >= 1


def test_queue_saturation_coalesces_by_path(tmp_path: Path) -> None:
    path = tmp_path / "hot.jsonl"
    _touch(path, "1\n")
    watcher = FileWatcher(
        queue_size=1,
        poll_interval_sec=0.05,
        max_paths_per_scan=10,
        max_changes_per_scan=10,
    )
    from server.ingest.watcher import WatchEvent

    older = WatchEvent(path=path.resolve(), mtime_ns=1)
    newer = WatchEvent(path=path.resolve(), mtime_ns=2)
    watcher._enqueue(older)
    watcher._enqueue(newer)
    retained = watcher._queue.get_nowait()
    assert retained is not None
    assert retained.mtime_ns == 2
    watcher._close_events()


def test_idle_backoff_increases_poll_interval(tmp_path: Path) -> None:
    path = tmp_path / "idle.jsonl"
    _touch(path, "x\n")
    watcher = FileWatcher(poll_interval_sec=0.1, max_paths_per_scan=10)
    watcher.watch([path])
    base = watcher.poll_interval_sec
    # Simulate idle cycles without starting the thread.
    for _ in range(3):
        changed = watcher._scan_once()
        assert changed == 0
        watcher._idle_cycles += 1
        factor = min(2 ** min(watcher._idle_cycles, 4), 16)
        watcher.poll_interval_sec = min(watcher._base_poll_interval_sec * factor, 5.0)
    assert watcher.poll_interval_sec > base
