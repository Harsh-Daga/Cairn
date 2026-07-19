"""Accelerated resource soak probe (T06-10) — not an 8h stability claim."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from server.app import create_app
from server.config import Settings
from server.store.benchmark import PROFILES, generate_benchmark_ledger
from server.store.resource_soak import run_accelerated_resource_soak


def test_accelerated_resource_soak_reports_samples(tmp_path: Path) -> None:
    generate_benchmark_ledger(tmp_path / ".cairn" / "cairn.db", PROFILES["small"])
    app = create_app(Settings(workspace_root=tmp_path))
    with TestClient(app) as client:
        report = run_accelerated_resource_soak(
            client,
            duration_sec=3.0,
            sse_clients=2,
            sample_interval_sec=0.4,
        )
    assert report["schema"] == "cairn.resource_soak.v2"
    assert report["kind"] == "accelerated"
    assert report["samples"] >= 1
    assert report["windows"]["idle"]["thread_count"]["p50"] is not None
    assert report["windows"]["event_bus"]["sse_publish_count"] >= 1
    assert report["windows"]["jobs"]["submitted"] >= 1
    assert report["health_latency_ms"]["p50"] is not None
    assert report["sse_clients"] == 2
    assert "Accelerated" in report["limitation"]
    assert report["collection_mode_flip"]["ok"] is True
