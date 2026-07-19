"""Accelerated resource soak samples — not a multi-hour stability claim."""

from __future__ import annotations

import statistics
import sys
import threading
import time
from typing import Any

from fastapi.testclient import TestClient

from server.api.sse import EventBus

try:
    import resource
except ImportError:  # pragma: no cover
    resource = None  # type: ignore[assignment]


def _rss_bytes() -> int | None:
    if resource is None:
        return None
    raw = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # macOS: bytes; Linux: KiB
    return int(raw) if sys.platform == "darwin" else int(raw * 1024)


def _thread_count() -> int:
    return threading.active_count()


def _stats(values: list[float] | list[int]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p50": None, "max": None}
    ordered = sorted(float(v) for v in values)
    return {
        "min": round(ordered[0], 3),
        "p50": round(statistics.median(ordered), 3),
        "max": round(ordered[-1], 3),
    }


def run_accelerated_resource_soak(
    client: TestClient,
    *,
    duration_sec: float = 8.0,
    sse_clients: int = 4,
    sample_interval_sec: float = 0.5,
) -> dict[str, Any]:
    """Sample idle RSS, EventBus load, and job-queue churn for a short window.

    Uses the in-process ``EventBus`` (same backpressure path as ``/api/live/events``)
    because Starlette ``TestClient`` cannot cleanly interrupt an open SSE HTTP stream.
    This is an *accelerated* probe — not an eight-hour idle claim.
    """
    duration_sec = max(1.0, min(float(duration_sec), 120.0))
    sse_clients = max(1, min(int(sse_clients), 16))
    sample_interval_sec = max(0.1, float(sample_interval_sec))
    slice_sec = max(1.0, duration_sec / 3.0)

    # --- Idle window (publisher off) ---
    idle_rss: list[int] = []
    idle_threads: list[int] = []
    idle_deadline = time.perf_counter() + slice_sec
    while time.perf_counter() < idle_deadline:
        rss = _rss_bytes()
        if rss is not None:
            idle_rss.append(rss)
        idle_threads.append(_thread_count())
        time.sleep(sample_interval_sec)

    # --- EventBus load ---
    bus = EventBus()
    client_ids: list[str] = []
    for _ in range(sse_clients):
        client_id, _queue = bus.subscribe()
        client_ids.append(client_id)

    publish_count = 0
    stop_publish = threading.Event()

    def _publisher() -> None:
        nonlocal publish_count
        index = 0
        while not stop_publish.wait(0.05):
            bus.publish("trace-updated", {"trace_id": f"soak-{index}"})
            index += 1
            publish_count = index

    publisher = threading.Thread(target=_publisher, daemon=True)
    publisher.start()

    rss_samples: list[int] = []
    thread_samples: list[int] = []
    health_latencies_ms: list[float] = []
    load_deadline = time.perf_counter() + slice_sec
    while time.perf_counter() < load_deadline:
        started = time.perf_counter()
        health = client.get("/api/health")
        health_latencies_ms.append((time.perf_counter() - started) * 1000)
        health.raise_for_status()
        rss = _rss_bytes()
        if rss is not None:
            rss_samples.append(rss)
        thread_samples.append(_thread_count())
        for client_id in client_ids:
            bus.wait_for_event(client_id, timeout=0.01)
        time.sleep(sample_interval_sec)

    stop_publish.set()
    publisher.join(timeout=2.0)
    dropped_total = sum(bus.client_dropped(client_id) for client_id in client_ids)
    for client_id in client_ids:
        bus.unsubscribe(client_id)

    # --- Job queue window ---
    jobs_submitted = 0
    jobs_done = 0
    jobs_failed = 0
    job_latencies_ms: list[float] = []
    job_deadline = time.perf_counter() + slice_sec
    while time.perf_counter() < job_deadline:
        started = time.perf_counter()
        response = client.post("/api/actions/db_integrity", json={})
        jobs_submitted += 1
        if response.status_code < 400:
            jobs_done += 1
        else:
            jobs_failed += 1
        job_latencies_ms.append((time.perf_counter() - started) * 1000)
        time.sleep(sample_interval_sec)

    mode_flip: dict[str, Any] = {"ok": False}
    try:
        flip = client.post(
            "/api/actions/config_set",
            json={
                "operation": "set",
                "key": "collection.mode",
                "value": "manual",
                "scope": "workspace",
            },
        )
        mode_flip = {
            "ok": flip.status_code < 400,
            "status_code": flip.status_code,
        }
    except Exception as exc:  # noqa: BLE001
        mode_flip = {"ok": False, "error": type(exc).__name__}

    return {
        "schema": "cairn.resource_soak.v2",
        "kind": "accelerated",
        "duration_sec": duration_sec,
        "sse_clients": sse_clients,
        "windows": {
            "idle": {
                "samples": len(idle_rss) or len(idle_threads),
                "rss_bytes": _stats(idle_rss),
                "thread_count": _stats(idle_threads),
            },
            "event_bus": {
                "samples": len(health_latencies_ms),
                "rss_bytes": _stats(rss_samples),
                "thread_count": _stats(thread_samples),
                "health_latency_ms": _stats(health_latencies_ms),
                "sse_publish_count": publish_count,
                "sse_dropped_events_total": dropped_total,
            },
            "jobs": {
                "submitted": jobs_submitted,
                "done": jobs_done,
                "failed": jobs_failed,
                "latency_ms": _stats(job_latencies_ms),
            },
        },
        # Back-compat flat fields for existing consumers.
        "samples": len(health_latencies_ms),
        "rss_bytes": _stats(rss_samples),
        "thread_count": _stats(thread_samples),
        "health_latency_ms": _stats(health_latencies_ms),
        "sse_publish_count": publish_count,
        "sse_dropped_events_total": dropped_total,
        "collection_mode_flip": mode_flip,
        "limitation": (
            "Accelerated wall-clock probe with idle RSS, in-process EventBus subscribers, "
            "and sync action latency samples. Does not claim eight-hour idle soak, HTTP "
            "multi-client SSE load, disk-full recovery, or production guarantees."
        ),
    }
