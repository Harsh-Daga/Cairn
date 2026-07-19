"""Bounded background job executor with dedupe, cancel, expiry, and backpressure."""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from server.api.sse import EventBus
from server.store.db import Database
from server.util.ids import new_ulid

JobStatus = Literal["pending", "running", "done", "error", "cancelled", "rejected"]
ProgressFn = Callable[[float, str], None]
JobFn = Callable[[ProgressFn], dict[str, Any]]

DEFAULT_MAX_WORKERS = 2
DEFAULT_MAX_QUEUED = 8
DEFAULT_RESULT_TTL_SEC = 3600.0
DEFAULT_JOB_TIMEOUT_SEC = 900.0


class JobSaturatedError(RuntimeError):
    """Raised when the job queue cannot accept more work."""


class JobCancelled(RuntimeError):
    """Raised inside a job when cancellation is requested."""


@dataclass
class JobHandle:
    """Cooperative cancellation token for long-running actions."""

    job_id: str
    _cancel: threading.Event = field(repr=False)

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def check(self) -> None:
        if self.cancelled():
            raise JobCancelled(f"job {self.job_id} cancelled")


@dataclass
class JobRecord:
    """In-memory job state."""

    job_id: str
    action: str
    status: JobStatus = "pending"
    progress: float = 0.0
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    dedupe_key: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None


class JobRunner:
    """Bounded executor for long actions with SSE progress and graceful shutdown."""

    def __init__(
        self,
        database: Database,
        event_bus: EventBus,
        *,
        max_workers: int = DEFAULT_MAX_WORKERS,
        max_queued: int = DEFAULT_MAX_QUEUED,
        result_ttl_sec: float = DEFAULT_RESULT_TTL_SEC,
        default_timeout_sec: float | None = DEFAULT_JOB_TIMEOUT_SEC,
    ) -> None:
        self._db = database  # reserved for future durable job ledger
        self._bus = event_bus
        self._max_workers = max(1, int(max_workers))
        self._max_queued = max(1, int(max_queued))
        self._result_ttl_sec = max(60.0, float(result_ttl_sec))
        self._default_timeout_sec = default_timeout_sec
        self._jobs: dict[str, JobRecord] = {}
        self._futures: dict[str, Future[None]] = {}
        self._cancels: dict[str, threading.Event] = {}
        self._active_dedupe: dict[str, str] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="cairn-job",
        )
        self._closed = False

    def submit(
        self,
        action: str,
        fn: JobFn,
        *,
        dedupe_key: str | None = None,
        timeout_sec: float | None = None,
    ) -> str:
        """Enqueue a job. Raises JobSaturatedError when the queue is full."""
        key = dedupe_key or action
        with self._lock:
            if self._closed:
                raise JobSaturatedError("Job runner is shutting down")
            self._prune_locked()
            existing_id = self._active_dedupe.get(key)
            if existing_id is not None:
                existing = self._jobs.get(existing_id)
                if existing is not None and existing.status in {"pending", "running"}:
                    return existing_id
            queued = sum(1 for job in self._jobs.values() if job.status in {"pending", "running"})
            if queued >= self._max_queued:
                raise JobSaturatedError(
                    f"Job queue saturated ({queued}/{self._max_queued}); retry after a job finishes"
                )
            job_id = new_ulid()
            record = JobRecord(job_id=job_id, action=action, status="pending", dedupe_key=key)
            cancel = threading.Event()
            self._jobs[job_id] = record
            self._cancels[job_id] = cancel
            self._active_dedupe[key] = job_id
            timeout = timeout_sec if timeout_sec is not None else self._default_timeout_sec
            future = self._executor.submit(self._run_job, job_id, fn, cancel, timeout)
            self._futures[job_id] = future
        self._emit(job_id)
        return job_id

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            self._prune_locked()
            record = self._jobs.get(job_id)
            if record is None:
                return None
            return JobRecord(
                job_id=record.job_id,
                action=record.action,
                status=record.status,
                progress=record.progress,
                message=record.message,
                result=record.result,
                error=record.error,
                dedupe_key=record.dedupe_key,
                created_at=record.created_at,
                updated_at=record.updated_at,
                finished_at=record.finished_at,
            )

    def cancel(self, job_id: str) -> JobRecord | None:
        """Request cooperative cancellation; pending jobs flip immediately."""
        with self._lock:
            record = self._jobs.get(job_id)
            cancel = self._cancels.get(job_id)
            if record is None:
                return None
            if record.status in {"done", "error", "cancelled", "rejected"}:
                return self.get(job_id)
            if cancel is not None:
                cancel.set()
            if record.status == "pending":
                record.status = "cancelled"
                record.message = "cancelled before start"
                record.finished_at = datetime.now(UTC).isoformat()
                record.updated_at = record.finished_at
                self._release_dedupe_locked(record)
        self._emit(job_id)
        return self.get(job_id)

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._prune_locked()
            by_status: dict[str, int] = {}
            for job in self._jobs.values():
                by_status[job.status] = by_status.get(job.status, 0) + 1
            return {
                "max_workers": self._max_workers,
                "max_queued": self._max_queued,
                "active": sum(
                    1 for job in self._jobs.values() if job.status in {"pending", "running"}
                ),
                "tracked": len(self._jobs),
                "by_status": by_status,
                "closed": self._closed,
                "limitation": (
                    "In-memory job ledger only; results expire after TTL. "
                    "Cancellation is cooperative (handlers must check JobHandle)."
                ),
            }

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = True) -> None:
        """Stop accepting work and optionally cancel in-flight jobs."""
        with self._lock:
            self._closed = True
            if cancel_pending:
                for job_id, cancel in self._cancels.items():
                    record = self._jobs.get(job_id)
                    if record is not None and record.status in {"pending", "running"}:
                        cancel.set()
                        if record.status == "pending":
                            record.status = "cancelled"
                            record.message = "cancelled on shutdown"
                            record.finished_at = datetime.now(UTC).isoformat()
                            record.updated_at = record.finished_at
                            self._release_dedupe_locked(record)
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def _run_job(
        self,
        job_id: str,
        fn: JobFn,
        cancel: threading.Event,
        timeout_sec: float | None,
    ) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None or record.status == "cancelled":
                return
            record.status = "running"
            record.updated_at = datetime.now(UTC).isoformat()
            handle = JobHandle(job_id=job_id, _cancel=cancel)
        self._emit(job_id)
        started = time.monotonic()
        progress = self._progress_cb(job_id, handle, started=started, timeout_sec=timeout_sec)

        try:
            handle.check()
            # Handlers may read cooperative cancel via getattr(progress, "__cairn_handle__").
            progress_any: Any = progress
            progress_any.__cairn_handle__ = handle
            result = fn(progress)
            if (
                timeout_sec is not None
                and timeout_sec > 0
                and time.monotonic() - started > timeout_sec
            ):
                cancel.set()
                raise TimeoutError(f"job exceeded {timeout_sec:.0f}s timeout")
            with self._lock:
                record = self._jobs.get(job_id)
                if record is None:
                    return
                if cancel.is_set() and record.status != "done":
                    record.status = "cancelled"
                    record.message = record.message or "cancelled"
                else:
                    record.status = "done"
                    record.progress = 1.0
                    record.result = result if isinstance(result, dict) else {"ok": True}
                record.finished_at = datetime.now(UTC).isoformat()
                record.updated_at = record.finished_at
                self._release_dedupe_locked(record)
        except JobCancelled:
            with self._lock:
                record = self._jobs.get(job_id)
                if record is not None:
                    record.status = "cancelled"
                    record.message = "cancelled"
                    record.finished_at = datetime.now(UTC).isoformat()
                    record.updated_at = record.finished_at
                    self._release_dedupe_locked(record)
        except TimeoutError as exc:
            with self._lock:
                record = self._jobs.get(job_id)
                if record is not None:
                    record.status = "error"
                    record.error = str(exc)
                    record.message = "timeout"
                    record.finished_at = datetime.now(UTC).isoformat()
                    record.updated_at = record.finished_at
                    self._release_dedupe_locked(record)
        except Exception as exc:  # noqa: BLE001 — surface to job record
            with self._lock:
                record = self._jobs.get(job_id)
                if record is not None:
                    record.status = "cancelled" if cancel.is_set() else "error"
                    record.error = str(exc)
                    record.message = traceback.format_exc(limit=3)
                    record.finished_at = datetime.now(UTC).isoformat()
                    record.updated_at = record.finished_at
                    self._release_dedupe_locked(record)
        finally:
            with self._lock:
                self._futures.pop(job_id, None)
            self._emit(job_id)

    def _progress_cb(
        self,
        job_id: str,
        handle: JobHandle,
        *,
        started: float,
        timeout_sec: float | None,
    ) -> ProgressFn:
        def _update(progress: float, message: str = "") -> None:
            handle.check()
            if (
                timeout_sec is not None
                and timeout_sec > 0
                and time.monotonic() - started > timeout_sec
            ):
                handle._cancel.set()
                raise TimeoutError(f"job exceeded {timeout_sec:.0f}s timeout")
            with self._lock:
                record = self._jobs.get(job_id)
                if record is None or record.status not in {"pending", "running"}:
                    return
                record.progress = max(0.0, min(1.0, progress))
                if message:
                    record.message = message
                record.updated_at = datetime.now(UTC).isoformat()
            self._emit(job_id)

        return _update

    def _release_dedupe_locked(self, record: JobRecord) -> None:
        key = record.dedupe_key or record.action
        if self._active_dedupe.get(key) == record.job_id:
            del self._active_dedupe[key]

    def _prune_locked(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=self._result_ttl_sec)
        stale: list[str] = []
        for job_id, record in self._jobs.items():
            if record.status not in {"done", "error", "cancelled", "rejected"}:
                continue
            finished = record.finished_at or record.updated_at
            try:
                finished_dt = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            except ValueError:
                continue
            if finished_dt < cutoff:
                stale.append(job_id)
        for job_id in stale:
            self._jobs.pop(job_id, None)
            self._cancels.pop(job_id, None)
            self._futures.pop(job_id, None)

    def _emit(self, job_id: str) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            payload = {
                "job_id": job_id,
                "action": record.action,
                "status": record.status,
                "progress": record.progress,
                "message": record.message,
                "error": record.error,
            }
        self._bus.publish("job-progress", payload)


def wait_for_job(
    runner: JobRunner,
    job_id: str,
    *,
    timeout_sec: float = 30.0,
    poll_sec: float = 0.05,
) -> JobRecord | None:
    """Test helper: poll until a job leaves pending/running."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        record = runner.get(job_id)
        if record is None or record.status not in {"pending", "running"}:
            return record
        time.sleep(poll_sec)
    return runner.get(job_id)
