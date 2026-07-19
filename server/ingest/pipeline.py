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
from server.configuration import load_config
from server.ingest.circuit_breakers import (
    assess_pre_parse,
    note_failure,
    note_success,
    quarantine_path,
    resources_config,
    run_parse_with_budget,
)
from server.ingest.collection import (
    CollectionRuntime,
    collection_status,
    resolve_collection_runtime,
)
from server.ingest.contract import Adapter, cursor_for_file
from server.ingest.contract import IngestCursor as ContractCursor
from server.ingest.parse_health import (
    inspect_unknown_fields,
    record_parse_attempt,
    reset_parse_health,
    unknown_field_spike,
)
from server.ingest.registry import build_adapters
from server.ingest.watcher import FileWatcher
from server.ingest.writer import IngestResult, IngestWriter
from server.mcp.consultations import import_consultations
from server.models.ingest import IngestCursor as StoredCursor
from server.store.db import Database
from server.store.repos.ingest_cursors import IngestCursorRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo

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
        self._runtime = resolve_collection_runtime(load_config(self.workspace_root).collection.mode)
        self._watcher = FileWatcher(poll_interval_sec=self._runtime.poll_interval_sec or 1.5)
        self._worker: threading.Thread | None = None
        self._refresh: threading.Thread | None = None
        self._stop = threading.Event()
        self._ingest_lock = threading.Lock()
        self._started = False

    @property
    def collection_runtime(self) -> CollectionRuntime:
        return self._runtime

    def status(self, *, sse_subscribers: int | None = None) -> dict[str, object]:
        running = bool(
            self._started
            and self._runtime.auto_sync_enabled
            and (
                (self._worker is not None and self._worker.is_alive())
                or (self._refresh is not None and self._refresh.is_alive())
            )
        )
        scan = self._watcher.stats()
        status = collection_status(
            runtime=self._runtime,
            auto_sync_running=running,
            watched_paths=len(self._path_adapter),
            sse_subscribers=sse_subscribers,
        )
        status["watcher"] = {
            "paths_checked": scan.paths_checked,
            "paths_deferred": scan.paths_deferred,
            "changed_files": scan.changed_files,
            "missing_files": scan.missing_files,
            "pruned_stale": scan.pruned_stale,
            "duration_ms": scan.duration_ms,
            "poll_interval_sec": scan.poll_interval_sec,
            "dropped_events": scan.dropped_events,
            "event_path": "queue",
            "limitation": (
                "Adaptive poll with path coalescing and per-cycle catch-up caps; "
                "not a native FS-event watcher. Idle backoff is measured locally "
                "and is not a soak guarantee."
            ),
        }
        return status

    def apply_collection_mode(self, mode: str) -> dict[str, object]:
        """Apply Manual / Efficient / Live and (re)start background loops as needed."""
        if self._started:
            self._stop_background(final=False)
            self._started = False
        self._runtime = resolve_collection_runtime(mode)
        self._watcher = FileWatcher(poll_interval_sec=self._runtime.poll_interval_sec or 1.0)
        self.start()
        return self.status()

    def reload_collection_mode(self) -> CollectionRuntime:
        """Reload mode from config and restart background loops if already started."""
        self.apply_collection_mode(load_config(self.workspace_root).collection.mode)
        return self._runtime

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
        """Start background collection according to the configured mode."""
        self._runtime = resolve_collection_runtime(load_config(self.workspace_root).collection.mode)
        self._stop.clear()
        self._started = True
        if not self._runtime.watcher_enabled and not self._runtime.refresh_enabled:
            # Manual: Sync now / cairn sync only.
            return
        if self._runtime.watcher_enabled:
            self._watcher.set_poll_interval(self._runtime.poll_interval_sec)
            self.watch_paths()
            self._watcher.start()
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._event_loop, name="cairn-ingest", daemon=True
                )
                self._worker.start()
        if self._runtime.refresh_enabled and (
            self._refresh is None or not self._refresh.is_alive()
        ):
            self._refresh = threading.Thread(
                target=self._refresh_loop, name="cairn-ingest-refresh", daemon=True
            )
            self._refresh.start()

    def stop(self) -> None:
        """Stop watcher and worker threads (process shutdown)."""
        self._stop_background(final=True)
        self._started = False

    def _stop_background(self, *, final: bool) -> None:
        """Stop auto-sync threads; close cost-tick publisher only on final shutdown."""
        self._stop.set()
        self._watcher.stop()
        if final:
            self._bus.cost_ticks.close()
        if self._worker is not None:
            self._worker.join(timeout=2)
            self._worker = None
        if self._refresh is not None:
            self._refresh.join(timeout=2)
            self._refresh = None

    def _refresh_loop(self) -> None:
        """Rediscover and ingest paths so newly created sessions are not missed."""
        while not self._stop.is_set():
            if not self._runtime.refresh_enabled:
                break
            try:
                self.sync_all()
            except Exception:
                # A malformed or temporarily unavailable adapter stream must not
                # permanently stop auto-sync for every other adapter.
                _LOGGER.exception("Background agent-log sync failed")
            interval = self._runtime.refresh_interval_sec or 45.0
            if self._stop.wait(interval):
                break

    def sync_all(
        self,
        source: str | None = None,
        *,
        force: bool = False,
        since: datetime | None = None,
    ) -> PipelineReport:
        """Scan all adapter streams and ingest new/changed files (Sync now).

        When ``force`` is true, re-parse even if the file cursor is unchanged so
        parser upgrades refresh traces and parse-health.

        When ``since`` is set, skip streams whose file mtime is older than that
        bound (used by backfill ``days``).
        """
        self.watch_paths()
        if force:
            # Rebuild coverage from this pass only (single wipe, then re-record).
            self._db.write(lambda conn: reset_parse_health(conn, workspace_id=self.workspace_id))
        report = PipelineReport()
        requested_source = source.replace("-", "_") if source else None
        # Snapshot paths — background refresh/watch_paths may mutate `_path_adapter`.
        pending = list(self._path_adapter.items())
        since_ts = since.timestamp() if since is not None else None
        for path, (adapter, detected_source) in pending:
            if requested_source and detected_source.replace("-", "_") != requested_source:
                continue
            if since_ts is not None:
                try:
                    if path.stat().st_mtime < since_ts:
                        report.skipped += 1
                        continue
                except OSError:
                    report.skipped += 1
                    continue
            report.scanned += 1
            result = self._ingest_path(path, adapter, detected_source, force=force)
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

    def ingest_path(self, path: Path, *, force: bool = False) -> IngestResult | None:
        """Ingest one file if an adapter owns it."""
        resolved = path.resolve()
        entry = self._path_adapter.get(resolved)
        if entry is None:
            self._refresh_path_index()
            entry = self._path_adapter.get(resolved)
        if entry is None:
            return None
        adapter, source = entry
        return self._ingest_path(resolved, adapter, source, force=force)

    def register_path(self, path: Path, adapter: Adapter, source: str) -> None:
        """Register one explicit adapter-owned path for harnesses and focused ingest."""
        self._path_adapter[path.resolve()] = (adapter, source)

    def _event_loop(self) -> None:
        """Sole consumer of watcher events (no synchronous callback ingest)."""
        for event in self._watcher.events():
            if self._stop.is_set():
                break
            entry = self._path_adapter.get(event.path.resolve())
            if entry is None:
                continue
            adapter, source = entry
            self._ingest_path(event.path.resolve(), adapter, source)

    def _ingest_path(
        self,
        path: Path,
        adapter: Adapter,
        source: str,
        *,
        force: bool = False,
    ) -> IngestResult | None:
        with self._ingest_lock:
            return self._ingest_path_locked(path, adapter, source, force=force)

    def _ingest_path_locked(
        self,
        path: Path,
        adapter: Adapter,
        source: str,
        *,
        force: bool = False,
    ) -> IngestResult | None:
        stream = str(path)
        stored = IngestCursorRepo.get(self._db.reader, source, stream)
        contract_cursor = self._load_contract_cursor(stored)
        self._maybe_record_source_drift(path, adapter.adapter_id, contract_cursor, stored)
        if not path.is_file():
            return None
        file_cursor = cursor_for_file(path)
        if (
            not force
            and stored is not None
            and self._cursor_unchanged(contract_cursor, file_cursor)
        ):
            return None

        decision = assess_pre_parse(
            path,
            workspace_root=self.workspace_root,
            adapter_id=adapter.adapter_id,
        )
        if not decision.allow:
            if decision.reason in {"file_too_large", "parse_timeout", "parse_error"}:
                quarantine_path(
                    self.workspace_root,
                    adapter_id=adapter.adapter_id,
                    path=path,
                    reason=decision.reason,
                    detail=decision.detail,
                    file_bytes=decision.file_bytes,
                )
            note_failure(
                self.workspace_root,
                adapter_id=adapter.adapter_id,
                reason=decision.reason,
                detail=decision.detail,
            )
            self._record_parse_health(adapter.adapter_id, "skipped")
            _LOGGER.warning(
                "%s circuit breaker blocked %s (%s: %s)",
                adapter.adapter_id,
                path,
                decision.reason,
                decision.detail,
            )
            return None

        cfg = resources_config(self.workspace_root)
        parsed, fail_reason, fail_detail = run_parse_with_budget(
            lambda: adapter.parse_path(path),
            max_parse_ms=cfg.max_parse_ms,
        )
        if fail_reason is not None:
            quarantine_path(
                self.workspace_root,
                adapter_id=adapter.adapter_id,
                path=path,
                reason=fail_reason,
                detail=fail_detail,
                file_bytes=decision.file_bytes,
            )
            note_failure(
                self.workspace_root,
                adapter_id=adapter.adapter_id,
                reason=fail_reason,
                detail=fail_detail,
            )
            self._record_parse_health(adapter.adapter_id, "skipped")
            _LOGGER.warning(
                "%s parse budget/error on %s (%s: %s)",
                adapter.adapter_id,
                path,
                fail_reason,
                fail_detail,
            )
            return None

        new_contract = file_cursor
        if parsed is None:
            self._record_parse_health(adapter.adapter_id, "skipped")
            self._persist_cursor(source, stream, new_contract)
            return None

        note_success(self.workspace_root, adapter_id=adapter.adapter_id)
        unknown_fields = inspect_unknown_fields(adapter.adapter_id, path)
        # Benign new metadata keys should not mark a stream degraded — only a
        # spike (or dropped events) indicates a real format-change risk.
        outcome = (
            "degraded"
            if parsed.dropped_events or unknown_field_spike(unknown_fields)
            else "fully_parsed"
        )
        self._record_parse_health(adapter.adapter_id, outcome, unknown_fields)

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
        if trace is not None:
            self._bus.cost_ticks.observe(trace)
        if dirty_keys:
            payload: dict[str, object] = {"keys": dirty_keys, "trace_id": result.trace_id}
            if computed:
                payload["computed"] = computed
            self._bus.publish("views-updated", payload)
        return result

    def _record_parse_health(
        self,
        adapter_id: str,
        outcome: str,
        unknown_fields: dict[str, int] | None = None,
    ) -> None:
        self._db.write(
            lambda conn: record_parse_attempt(
                conn,
                workspace_id=self.workspace_id,
                adapter_id=adapter_id,
                outcome=outcome,
                unknown_fields=unknown_fields,
            )
        )

    def _maybe_record_source_drift(
        self,
        path: Path,
        adapter_id: str,
        contract_cursor: ContractCursor,
        stored: StoredCursor | None,
    ) -> None:
        """In reference mode, record missing/rewritten source logs (never mutate them)."""
        if stored is None:
            return
        from server.ingest.reference import detect_source_drift, record_drift
        from server.ingest.storage import normalize_storage_mode

        mode = normalize_storage_mode(load_config(self.workspace_root).storage.mode)
        if mode != "reference":
            return
        event = detect_source_drift(path, contract_cursor, adapter_id=adapter_id)
        if event is not None:
            record_drift(self.workspace_root, event)
            _LOGGER.warning(
                "reference source drift (%s) for %s: %s",
                event.kind,
                adapter_id,
                path,
            )

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
