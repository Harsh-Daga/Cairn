"""Ingest pipeline — watch, parse, write, dirty-mark, SSE."""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from server.analyze.dirty import mark_trace_dirty, trace_day_key
from server.analyze.registry import build_views
from server.analyze.views import ViewScheduler
from server.api.sse import EventBus
from server.ingest.contract import Adapter, cursor_for_file
from server.ingest.contract import IngestCursor as ContractCursor
from server.ingest.registry import build_adapters
from server.ingest.watcher import FileWatcher
from server.ingest.writer import IngestResult, IngestWriter
from server.mcp.consultations import import_consultations
from server.models.ingest import IngestCursor as StoredCursor
from server.store.db import Database
from server.store.repos.ingest_cursors import IngestCursorRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo

_PATH_REFRESH_SEC = 30.0
_LOGGER = logging.getLogger(__name__)


@dataclass
class PipelineReport:
    """Summary of one sync pass."""

    scanned: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    mcp_consultations: int = 0
    results: list[IngestResult] = field(default_factory=list)


class IngestPipeline:
    """Orchestrate adapter ingest with watcher, cursors, and live events."""

    def __init__(
        self,
        database: Database,
        workspace_id: str,
        workspace_root: Path,
        event_bus: EventBus,
    ) -> None:
        self._db = database
        self.workspace_id = workspace_id
        self.workspace_root = workspace_root.resolve()
        self._bus = event_bus
        self._writer = IngestWriter(database, workspace_id, self.workspace_root)
        self._adapters = build_adapters(self.workspace_root, workspace_id)
        self._path_adapter: dict[Path, tuple[Adapter, str]] = {}
        self._watcher = FileWatcher()
        self._watcher.set_on_change(self._on_path_changed)
        self._worker: threading.Thread | None = None
        self._refresh: threading.Thread | None = None
        self._stop = threading.Event()
        self._ingest_lock = threading.Lock()

    def _refresh_path_index(self) -> None:
        self._path_adapter.clear()
        for adapter in self._adapters:
            for ref in adapter.detect():
                self._path_adapter[ref.path.resolve()] = (adapter, ref.source)

    def watch_paths(self) -> list[Path]:
        """Return all adapter-declared paths and register them with the watcher."""
        self._refresh_path_index()
        paths = list(self._path_adapter.keys())
        self._watcher.watch(paths)
        return paths

    def start(self) -> None:
        """Start background watcher-driven ingest."""
        self._stop.clear()
        self._watcher.start()
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(
                target=self._event_loop, name="cairn-ingest", daemon=True
            )
            self._worker.start()
        if self._refresh is None or not self._refresh.is_alive():
            self._refresh = threading.Thread(
                target=self._refresh_loop, name="cairn-ingest-refresh", daemon=True
            )
            self._refresh.start()

    def stop(self) -> None:
        """Stop watcher and worker threads."""
        self._stop.set()
        self._watcher.stop()
        if self._worker is not None:
            self._worker.join(timeout=2)
            self._worker = None
        if self._refresh is not None:
            self._refresh.join(timeout=2)
            self._refresh = None

    def _refresh_loop(self) -> None:
        """Rediscover and ingest paths so newly created sessions are not missed."""
        while not self._stop.is_set():
            try:
                self.sync_all()
            except Exception:
                # A malformed or temporarily unavailable adapter stream must not
                # permanently stop auto-sync for every other adapter.
                _LOGGER.exception("Background agent-log sync failed")
            if self._stop.wait(_PATH_REFRESH_SEC):
                break

    def sync_all(self, source: str | None = None) -> PipelineReport:
        """Scan all adapter streams and ingest new/changed files."""
        self.watch_paths()
        report = PipelineReport()
        requested_source = source.replace("-", "_") if source else None
        for path, (adapter, detected_source) in self._path_adapter.items():
            if requested_source and detected_source.replace("-", "_") != requested_source:
                continue
            report.scanned += 1
            result = self._ingest_path(path, adapter, detected_source)
            if result is None:
                report.skipped += 1
                continue
            report.results.append(result)
            if result.inserted:
                report.inserted += 1
            else:
                report.updated += 1
        report.mcp_consultations = self._db.write(
            lambda conn: import_consultations(conn, self.workspace_root, self.workspace_id)
        )
        if report.mcp_consultations:
            self._bus.publish(
                "views-updated",
                {"mcp_consultations": report.mcp_consultations},
            )
        return report

    def ingest_path(self, path: Path) -> IngestResult | None:
        """Ingest one file if an adapter owns it."""
        resolved = path.resolve()
        entry = self._path_adapter.get(resolved)
        if entry is None:
            self._refresh_path_index()
            entry = self._path_adapter.get(resolved)
        if entry is None:
            return None
        adapter, source = entry
        return self._ingest_path(resolved, adapter, source)

    def _event_loop(self) -> None:
        for event in self._watcher.events():
            if self._stop.is_set():
                break
            entry = self._path_adapter.get(event.path.resolve())
            if entry is None:
                continue
            adapter, source = entry
            self._ingest_path(event.path.resolve(), adapter, source)

    def _on_path_changed(self, path: Path) -> None:
        entry = self._path_adapter.get(path.resolve())
        if entry is None:
            return
        adapter, source = entry
        self._ingest_path(path.resolve(), adapter, source)

    def _ingest_path(self, path: Path, adapter: Adapter, source: str) -> IngestResult | None:
        with self._ingest_lock:
            return self._ingest_path_locked(path, adapter, source)

    def _ingest_path_locked(
        self, path: Path, adapter: Adapter, source: str
    ) -> IngestResult | None:
        if not path.is_file():
            return None
        stream = str(path)
        stored = IngestCursorRepo.get(self._db.reader, source, stream)
        contract_cursor = self._load_contract_cursor(stored)
        file_cursor = cursor_for_file(path)
        if stored is not None and self._cursor_unchanged(contract_cursor, file_cursor):
            return None

        parsed = adapter.parse_path(path)
        new_contract = file_cursor
        if parsed is None:
            self._persist_cursor(source, stream, new_contract)
            return None

        result = self._writer.ingest(parsed)
        self._persist_cursor(source, stream, new_contract)
        trace = TraceRepo.get(self._db.reader, result.trace_id)
        project = trace.project if trace is not None else None
        day = trace_day_key(trace.started_at if trace is not None else None)

        def _mark_dirty(conn: sqlite3.Connection) -> list[str]:
            return mark_trace_dirty(conn, result.trace_id, day=day, project=project or "")

        dirty_keys = self._db.write(_mark_dirty)
        computed = self._run_scheduler(dirty_keys)
        spans = SpanRepo.list_by_trace(self._db.reader, result.trace_id)
        latest = spans[-1] if spans else None
        self._bus.publish(
            "trace-updated",
            {
                "trace_id": result.trace_id,
                "inserted": result.inserted,
                "span_count": result.span_count,
                "source": source,
                "span_id": latest.span_id if latest is not None else None,
                "kind": latest.kind if latest is not None else None,
            },
        )
        if dirty_keys:
            payload: dict[str, object] = {"keys": dirty_keys, "trace_id": result.trace_id}
            if computed:
                payload["computed"] = computed
            self._bus.publish("views-updated", payload)
        return result

    def _run_scheduler(self, dirty_keys: list[str]) -> list[str]:
        if not dirty_keys:
            return []

        def _compute(conn: sqlite3.Connection) -> list[str]:
            scheduler = ViewScheduler(conn, build_views(self.workspace_id))
            return scheduler.run(dirty_keys)

        return self._db.write(_compute)

    @staticmethod
    def _load_contract_cursor(stored: StoredCursor | None) -> ContractCursor:
        if stored is None:
            return ContractCursor()
        return ContractCursor.from_json(stored.cursor)

    @staticmethod
    def _cursor_unchanged(old: ContractCursor, new: ContractCursor) -> bool:
        return old.offset == new.offset and old.mtime_ns == new.mtime_ns and old.size == new.size

    def _persist_cursor(self, source: str, stream: str, cursor: ContractCursor) -> None:
        now = datetime.now(UTC).isoformat()
        row = StoredCursor(
            source=source,
            stream=stream,
            cursor=cursor.to_json(),
            updated_at=now,
        )

        def _upsert(conn: sqlite3.Connection) -> None:
            IngestCursorRepo.upsert(conn, row)

        self._db.write(_upsert)
