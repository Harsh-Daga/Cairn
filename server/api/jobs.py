"""Background job runner for long-running actions."""

from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from server.api.sse import EventBus
from server.store.db import Database
from server.util.ids import new_ulid

JobStatus = Literal["pending", "running", "done", "error"]


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
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class JobRunner:
    """Run long actions on a background thread and emit SSE progress."""

    def __init__(self, database: Database, event_bus: EventBus) -> None:
        self._db = database
        self._bus = event_bus
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def submit(self, action: str, fn: Any) -> str:
        """Start a background job and return its id."""
        job_id = new_ulid()
        record = JobRecord(job_id=job_id, action=action, status="running")
        with self._lock:
            self._jobs[job_id] = record
        self._emit(job_id, record)

        def _run() -> None:
            try:
                result = fn(self._progress_cb(job_id))
                record.status = "done"
                record.progress = 1.0
                record.result = result if isinstance(result, dict) else {"ok": True}
            except Exception as exc:  # noqa: BLE001 — surface to job record
                record.status = "error"
                record.error = str(exc)
                record.message = traceback.format_exc(limit=3)
            self._emit(job_id, record)

        threading.Thread(target=_run, name=f"cairn-job-{action}", daemon=True).start()
        return job_id

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _progress_cb(self, job_id: str) -> Callable[[float, str], None]:
        def _update(progress: float, message: str = "") -> None:
            with self._lock:
                record = self._jobs.get(job_id)
                if record is None:
                    return
                record.progress = max(0.0, min(1.0, progress))
                if message:
                    record.message = message
            self._emit(job_id, record)

        return _update

    def _emit(self, job_id: str, record: JobRecord | None) -> None:
        if record is None:
            return
        self._bus.publish(
            "job-progress",
            {
                "job_id": job_id,
                "action": record.action,
                "status": record.status,
                "progress": record.progress,
                "message": record.message,
                "error": record.error,
            },
        )
