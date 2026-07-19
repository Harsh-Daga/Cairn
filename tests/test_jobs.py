"""Bounded job executor: dedupe, saturation, cancel, progress, shutdown."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from server.api.jobs import JobCancelled, JobRunner, JobSaturatedError, wait_for_job
from server.api.sse import EventBus
from server.store.db import Database
from server.util.ids import new_ulid


@pytest.fixture
def runner(tmp_path: Path) -> JobRunner:
    root = tmp_path / "ws"
    root.mkdir()
    cairn = root / ".cairn"
    cairn.mkdir()
    db = Database(cairn / "cairn.db")
    ws_id = new_ulid()
    db.write(
        lambda conn: conn.execute(
            "INSERT INTO workspaces (workspace_id, root_path, name, created_at) "
            "VALUES (?, ?, ?, ?)",
            (ws_id, str(root), "jobs", "2026-07-01T00:00:00Z"),
        )
    )
    jobs = JobRunner(
        db,
        EventBus(),
        max_workers=1,
        max_queued=2,
        result_ttl_sec=60,
        default_timeout_sec=5,
    )
    yield jobs
    jobs.shutdown(wait=True, cancel_pending=True)
    db.close()


def test_submit_runs_and_reports_progress(runner: JobRunner) -> None:
    def work(progress: object) -> dict[str, object]:
        progress(0.5, "halfway")  # type: ignore[operator]
        return {"ok": True, "value": 7}

    job_id = runner.submit("rebuild_view", work)
    record = wait_for_job(runner, job_id, timeout_sec=5)
    assert record is not None
    assert record.status == "done"
    assert record.result == {"ok": True, "value": 7}


def test_dedupe_returns_same_job_id(runner: JobRunner) -> None:
    gate = threading.Event()

    def work(progress: object) -> dict[str, object]:
        gate.wait(timeout=2)
        return {"ok": True}

    first = runner.submit("sync", work, dedupe_key="sync")
    second = runner.submit("sync", work, dedupe_key="sync")
    assert first == second
    gate.set()
    wait_for_job(runner, first, timeout_sec=5)


def test_saturation_raises(runner: JobRunner) -> None:
    gate = threading.Event()

    def work(progress: object) -> dict[str, object]:
        gate.wait(timeout=3)
        return {"ok": True}

    runner.submit("a", work, dedupe_key="a")
    runner.submit("b", work, dedupe_key="b")
    with pytest.raises(JobSaturatedError):
        runner.submit("c", work, dedupe_key="c")
    gate.set()


def test_cancel_cooperative(runner: JobRunner) -> None:
    started = threading.Event()

    def work(progress: object) -> dict[str, object]:
        started.set()
        for _ in range(50):
            handle = getattr(progress, "__cairn_handle__", None)
            if handle is not None and handle.cancelled():
                raise JobCancelled("stopped")
            progress(0.2, "working")  # type: ignore[operator]
            time.sleep(0.05)
        return {"ok": True}

    job_id = runner.submit("backfill", work, dedupe_key="backfill")
    assert started.wait(timeout=2)
    cancelled = runner.cancel(job_id)
    assert cancelled is not None
    record = wait_for_job(runner, job_id, timeout_sec=5)
    assert record is not None
    assert record.status == "cancelled"


def test_shutdown_rejects_new_work(runner: JobRunner) -> None:
    runner.shutdown(wait=False, cancel_pending=True)
    with pytest.raises(JobSaturatedError):
        runner.submit("sync", lambda _p: {"ok": True})
