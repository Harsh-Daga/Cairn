"""Metrics compute — v3 delegates to backfill."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cairn.ingest.backfill import backfill_run, recompute_rollups


def backfill_session_metrics(writer: Any, run_id: str) -> None:
    backfill_run(writer, run_id)


def recompute_all_rollups(project_root: Path, *, days: int = 90) -> None:
    from cairn.ingest.writer import CaptureWriter

    writer = CaptureWriter(project_root)
    try:
        recompute_rollups(writer, days=days)
    finally:
        writer.close()
