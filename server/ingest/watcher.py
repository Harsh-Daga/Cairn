"""Polling file watcher with a single coalesced event path and stale-path pruning."""

from __future__ import annotations

import contextlib
import queue
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

QUEUE_SIZE = 256
_DEFAULT_POLL_INTERVAL_SEC = 0.5
_MIN_POLL_INTERVAL_SEC = 0.05
_MAX_IDLE_BACKOFF_SEC = 5.0
_DEBOUNCE_SEC = 0.05
# Cap work per poll so large historical watch sets cannot monopolize a cycle.
_MAX_PATHS_PER_SCAN = 512
_MAX_CHANGES_PER_SCAN = 64
# Drop paths that stay missing across consecutive scans (stale watches).
_MISSING_PRUNE_CYCLES = 3


@dataclass(frozen=True)
class WatchEvent:
    """Filesystem change notification."""

    path: Path
    mtime_ns: int


@dataclass(frozen=True)
class ScanStats:
    """Measured facts from the latest poll cycle (not a performance claim)."""

    scanned_at: float = 0.0
    duration_ms: float = 0.0
    paths_checked: int = 0
    paths_deferred: int = 0
    changed_files: int = 0
    missing_files: int = 0
    pruned_stale: int = 0
    watched_paths: int = 0
    dropped_events: int = 0
    poll_interval_sec: float = _DEFAULT_POLL_INTERVAL_SEC


class FileWatcher:
    """Poll watched paths and emit coalesced change events on one queue path."""

    def __init__(
        self,
        *,
        queue_size: int = QUEUE_SIZE,
        poll_interval_sec: float = _DEFAULT_POLL_INTERVAL_SEC,
        max_paths_per_scan: int = _MAX_PATHS_PER_SCAN,
        max_changes_per_scan: int = _MAX_CHANGES_PER_SCAN,
    ) -> None:
        self._queue: queue.Queue[WatchEvent | None] = queue.Queue(maxsize=queue_size)
        self._paths: dict[Path, int] = {}
        self._pending: dict[Path, WatchEvent] = {}
        self._missing_cycles: dict[Path, int] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._base_poll_interval_sec = max(_MIN_POLL_INTERVAL_SEC, float(poll_interval_sec))
        self.poll_interval_sec = self._base_poll_interval_sec
        self.max_paths_per_scan = max(1, int(max_paths_per_scan))
        self.max_changes_per_scan = max(1, int(max_changes_per_scan))
        self._idle_cycles = 0
        self._scan_cursor = 0
        self._dropped_events = 0
        self._stats = ScanStats(poll_interval_sec=self.poll_interval_sec)

    def set_poll_interval(self, seconds: float) -> None:
        """Update base poll cadence (idle backoff scales from this)."""
        base = max(_MIN_POLL_INTERVAL_SEC, float(seconds))
        with self._lock:
            self._base_poll_interval_sec = base
            self.poll_interval_sec = base
            self._idle_cycles = 0

    def watch(self, paths: list[Path]) -> None:
        """Replace the watch set (drops stale watches; preserves mtimes for known paths)."""
        desired = [raw.resolve() for raw in paths]
        with self._lock:
            new_paths: dict[Path, int] = {}
            for path in desired:
                if path in self._paths:
                    new_paths[path] = self._paths[path]
                else:
                    try:
                        new_paths[path] = path.stat().st_mtime_ns
                    except OSError:
                        new_paths[path] = 0
            for path in list(self._pending):
                if path not in new_paths:
                    del self._pending[path]
            for path in list(self._missing_cycles):
                if path not in new_paths:
                    del self._missing_cycles[path]
            self._paths = new_paths
            self._scan_cursor = 0

    def add_path(self, path: Path) -> None:
        """Add one path without removing the rest of the watch set."""
        resolved = path.resolve()
        try:
            mtime_ns = resolved.stat().st_mtime_ns
        except OSError:
            mtime_ns = 0
        with self._lock:
            if resolved not in self._paths:
                self._paths[resolved] = mtime_ns
            self._missing_cycles.pop(resolved, None)

    def start(self) -> None:
        """Start the polling thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="cairn-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop polling and close the event iterator."""
        self._stop.set()
        self._flush_pending()
        self._close_events()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _close_events(self) -> None:
        """Always deliver the iterator sentinel, even when the queue is saturated."""
        try:
            self._queue.put_nowait(None)
            return
        except queue.Full:
            pass
        # Drop one buffered event to make room for the stop sentinel.
        with contextlib.suppress(queue.Empty):
            self._queue.get_nowait()
            with self._lock:
                self._dropped_events += 1
        with contextlib.suppress(queue.Full):
            self._queue.put_nowait(None)

    def events(self) -> Iterator[WatchEvent]:
        """Blocking iterator over coalesced watch events (sole delivery path)."""
        while True:
            item = self._queue.get()
            if item is None:
                break
            yield item

    def stats(self) -> ScanStats:
        """Return the latest measured scan stats."""
        with self._lock:
            return self._stats

    def watched_paths(self) -> list[Path]:
        with self._lock:
            return list(self._paths.keys())

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            changed = self._scan_once()
            with self._lock:
                if changed:
                    self._idle_cycles = 0
                    self.poll_interval_sec = self._base_poll_interval_sec
                else:
                    self._idle_cycles += 1
                    # Adaptive idle backoff from base… capped. Not an idle-soak claim.
                    factor = min(2 ** min(self._idle_cycles, 4), 16)
                    self.poll_interval_sec = min(
                        self._base_poll_interval_sec * factor,
                        _MAX_IDLE_BACKOFF_SEC,
                    )
                sleep_for = self.poll_interval_sec
            if self._stop.wait(sleep_for):
                break

    def _scan_once(self) -> int:
        started = time.perf_counter()
        with self._lock:
            # Recently touched files first so active sessions win under catch-up pressure.
            ordered = sorted(self._paths.items(), key=lambda item: item[1], reverse=True)
            if not ordered:
                snapshot: list[tuple[Path, int]] = []
                deferred = 0
            else:
                start = self._scan_cursor % len(ordered)
                rotated = ordered[start:] + ordered[:start]
                snapshot = rotated[: self.max_paths_per_scan]
                deferred = max(0, len(rotated) - len(snapshot))
                self._scan_cursor = (start + len(snapshot)) % len(ordered)
        changed = 0
        missing = 0
        pruned = 0
        for path, last_mtime in snapshot:
            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                missing += 1
                with self._lock:
                    cycles = self._missing_cycles.get(path, 0) + 1
                    self._missing_cycles[path] = cycles
                    if cycles >= _MISSING_PRUNE_CYCLES and path in self._paths:
                        del self._paths[path]
                        self._pending.pop(path, None)
                        del self._missing_cycles[path]
                        pruned += 1
                continue
            with self._lock:
                self._missing_cycles.pop(path, None)
            if mtime_ns <= last_mtime:
                continue
            if changed >= self.max_changes_per_scan:
                deferred += 1
                continue
            with self._lock:
                self._paths[path] = mtime_ns
                self._pending[path] = WatchEvent(path=path, mtime_ns=mtime_ns)
            changed += 1
        duration_ms = (time.perf_counter() - started) * 1000.0
        with self._lock:
            self._stats = ScanStats(
                scanned_at=time.time(),
                duration_ms=round(duration_ms, 3),
                paths_checked=len(snapshot),
                paths_deferred=deferred,
                changed_files=changed,
                missing_files=missing,
                pruned_stale=pruned,
                watched_paths=len(self._paths),
                dropped_events=self._dropped_events,
                poll_interval_sec=self.poll_interval_sec,
            )
        if changed and _DEBOUNCE_SEC > 0:
            # Collapse burst appends into one pending event per path.
            time.sleep(_DEBOUNCE_SEC)
            self._refresh_pending_mtimes()
        self._flush_pending()
        return changed

    def _refresh_pending_mtimes(self) -> None:
        with self._lock:
            pending_paths = list(self._pending.keys())
        for path in pending_paths:
            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                continue
            with self._lock:
                self._paths[path] = mtime_ns
                self._pending[path] = WatchEvent(path=path, mtime_ns=mtime_ns)

    def _flush_pending(self) -> None:
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for event in pending:
            self._enqueue(event)

    def _enqueue(self, event: WatchEvent) -> None:
        try:
            self._queue.put_nowait(event)
            return
        except queue.Full:
            pass
        # Coalesce: keep newest event per path when the queue is saturated.
        retained: dict[Path, WatchEvent] = {}
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                retained[item.path] = item
        retained[event.path] = event
        dropped = 0
        for item in retained.values():
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                dropped += 1
        if dropped:
            with self._lock:
                self._dropped_events += dropped
