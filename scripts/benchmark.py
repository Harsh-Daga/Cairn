#!/usr/bin/env python3
"""Generate repeatable scale fixtures and report hardware-sensitive timings."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from server.api.bootstrap import bootstrap_runtime
from server.app import create_app
from server.config import Settings
from server.export.static import export_static_snapshot
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.store.benchmark import PROFILES, BenchmarkLedger, generate_benchmark_ledger
from server.store.dedup_assessment import assess_content_dedup
from server.store.resource_soak import run_accelerated_resource_soak

try:
    import resource
except ImportError:  # pragma: no cover - Windows has no stdlib resource module
    resource = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SAMPLES = 7


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percentile))
    return ordered[index]


def _rss_mib() -> float | None:
    if resource is None:
        return None
    raw = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # macOS reports bytes; Linux reports KiB.
    return raw / (1024 * 1024) if sys.platform == "darwin" else raw / 1024


def _cold_start_ms() -> float:
    started = time.perf_counter()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path;"
                "from server.app import create_app;"
                "from server.config import Settings;"
                "create_app(Settings(workspace_root=Path.cwd()))"
            ),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr)
    return (time.perf_counter() - started) * 1000


def _endpoint_timings(
    client: TestClient,
    path: str,
    *,
    samples: int,
) -> dict[str, float | int]:
    warm = client.get(path)
    warm.raise_for_status()
    timings: list[float] = []
    payload_bytes = len(warm.content)
    for _ in range(samples):
        started = time.perf_counter()
        response = client.get(path)
        elapsed = (time.perf_counter() - started) * 1000
        response.raise_for_status()
        timings.append(elapsed)
    return {
        "p50_ms": round(statistics.median(timings), 3),
        "p95_ms": round(_percentile(timings, 0.95), 3),
        "payload_bytes": payload_bytes,
    }


def _environment() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }


def _incremental_ingest_timing(workspace: Path) -> dict[str, float | bool]:
    fixture = ROOT / "tests" / "fixtures" / "ingest" / "claude_code_mini.jsonl"
    runtime = bootstrap_runtime(Settings(workspace_root=workspace))
    runtime.pipeline.register_path(
        fixture,
        ClaudeCodeAdapter(workspace, runtime.workspace_id),
        "claude_code",
    )
    try:
        started = time.perf_counter()
        first = runtime.pipeline.ingest_path(fixture)
        first_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        second = runtime.pipeline.ingest_path(fixture)
        incremental_ms = (time.perf_counter() - started) * 1000
    finally:
        runtime.database.close()
    return {
        "first_ingest_ms": round(first_ms, 3),
        "incremental_ingest_ms": round(incremental_ms, 3),
        "first_ingest_parsed": first is not None,
        "incremental_ingest_parsed": second is not None,
    }


def run_benchmark(
    workspace: Path,
    *,
    profile_name: str,
    samples: int = DEFAULT_SAMPLES,
    include_static: bool = False,
) -> dict[str, Any]:
    """Generate one profile and measure representative local journeys."""
    profile = PROFILES[profile_name]
    db_path = workspace / ".cairn" / "cairn.db"
    started = time.perf_counter()
    ledger = generate_benchmark_ledger(db_path, profile)
    generation_seconds = time.perf_counter() - started
    application = create_app(Settings(workspace_root=workspace))
    routes = {
        "health": "/api/health",
        "overview_30d": "/api/overview?days=30",
        "traces_200": "/api/traces?days=30&limit=200&offset=0",
        "search_pytest": "/api/search?q=pytest&limit=50",
        "regions_30d": "/api/analytics/regions?days=30",
        "quality_30d": "/api/quality?days=30",
        "wide_trace_detail": "/api/traces/bench-trace-000000",
        "wide_trace_replay": "/api/traces/bench-trace-000000/replay",
    }
    with TestClient(application) as client:
        timings = {
            name: _endpoint_timings(client, path, samples=samples) for name, path in routes.items()
        }
    report: dict[str, Any] = {
        "profile": profile.name,
        "environment": _environment(),
        "fixture": {
            "trace_count": ledger.trace_count,
            "span_count": ledger.span_count,
            "wide_trace_spans": profile.wide_trace_spans,
            "database_bytes": ledger.bytes,
            "generation_seconds": round(generation_seconds, 3),
            "generation_traces_per_second": round(ledger.trace_count / generation_seconds, 1),
        },
        "cold_start_ms": round(_cold_start_ms(), 3),
        "endpoints": timings,
        "ingest": _incremental_ingest_timing(workspace),
        "peak_rss_mib": round(rss, 2) if (rss := _rss_mib()) is not None else None,
    }
    if include_static:
        static_dir = workspace / "static-export"
        started = time.perf_counter()
        static_result = export_static_snapshot(workspace, static_dir)
        elapsed = time.perf_counter() - started
        report["static_export"] = {
            **static_result,
            "seconds": round(elapsed, 3),
            "bytes": sum(path.stat().st_size for path in static_dir.rglob("*") if path.is_file()),
            "peak_rss_mib": round(rss, 2) if (rss := _rss_mib()) is not None else None,
        }
    return report


def _generate(workspace: Path, profile_name: str) -> BenchmarkLedger:
    return generate_benchmark_ledger(
        workspace / ".cairn" / "cairn.db",
        PROFILES[profile_name],
    )


def _assess_dedup(workspace: Path, profile_name: str) -> dict[str, Any]:
    db_path = workspace / ".cairn" / "cairn.db"
    if not db_path.is_file():
        generate_benchmark_ledger(db_path, PROFILES[profile_name])
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        report = assess_content_dedup(conn)
    finally:
        conn.close()
    return {
        "profile": profile_name,
        "environment": _environment(),
        "assessment": report,
    }


def _resource_soak(
    workspace: Path,
    profile_name: str,
    *,
    duration_sec: float,
    sse_clients: int,
) -> dict[str, Any]:
    db_path = workspace / ".cairn" / "cairn.db"
    if not db_path.is_file():
        generate_benchmark_ledger(db_path, PROFILES[profile_name])
    application = create_app(Settings(workspace_root=workspace))
    with TestClient(application) as client:
        soak = run_accelerated_resource_soak(
            client,
            duration_sec=duration_sec,
            sse_clients=sse_clients,
        )
    return {
        "profile": profile_name,
        "environment": _environment(),
        "soak": soak,
        "peak_rss_mib": round(rss, 2) if (rss := _rss_mib()) is not None else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("generate", "run", "assess-dedup", "resource-soak"),
    )
    parser.add_argument("--profile", choices=tuple(PROFILES), default="small")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--include-static", action="store_true")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument(
        "--soak-seconds",
        type=float,
        default=8.0,
        help="Accelerated resource-soak wall time (1–120s; not an 8h claim).",
    )
    parser.add_argument("--sse-clients", type=int, default=4)
    args = parser.parse_args()
    if args.samples < 1 or args.samples > 100:
        parser.error("--samples must be between 1 and 100")
    if args.soak_seconds < 1 or args.soak_seconds > 120:
        parser.error("--soak-seconds must be between 1 and 120")
    if args.sse_clients < 1 or args.sse_clients > 16:
        parser.error("--sse-clients must be between 1 and 16")

    def _dispatch(workspace: Path) -> Any:
        if args.command == "generate":
            return _generate(workspace, args.profile)
        if args.command == "assess-dedup":
            return _assess_dedup(workspace, args.profile)
        if args.command == "resource-soak":
            return _resource_soak(
                workspace,
                args.profile,
                duration_sec=args.soak_seconds,
                sse_clients=args.sse_clients,
            )
        return run_benchmark(
            workspace,
            profile_name=args.profile,
            samples=args.samples,
            include_static=args.include_static,
        )

    if args.workspace is None:
        with tempfile.TemporaryDirectory(prefix="cairn-benchmark-") as temporary:
            workspace = Path(temporary)
            result = _dispatch(workspace)
            payload = asdict(result) if isinstance(result, BenchmarkLedger) else result
    else:
        workspace = args.workspace.expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        result = _dispatch(workspace)
        payload = asdict(result) if isinstance(result, BenchmarkLedger) else result
    serialized = json.dumps(payload, indent=2, default=str, sort_keys=True) + "\n"
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()
