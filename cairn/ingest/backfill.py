"""Recompute waste metrics and daily rollups for a run."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cairn.metrics.waste import compute_waste

if TYPE_CHECKING:
    from cairn.ingest.writer import CaptureWriter


def backfill_run(writer: CaptureWriter, run_id: str) -> None:
    """Run waste classification and update rollups for one session."""
    conn = writer.connection
    events = writer.load_events(run_id)
    row = conn.execute(
        "SELECT has_cost, source, project, model, started_at FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        return
    has_cost = bool(row["has_cost"])
    peak_pct = _peak_context_pct(events)
    # Pillar 1: context-region decomposition + re-billing tokens (feeds the
    # REBILLING_WASTE hook). Idempotent: clears prior region rows for the run.
    rebilling_tokens = _compute_rebilling(writer, run_id, events=events, model=row["model"])
    waste = compute_waste(
        events,
        has_cost=has_cost,
        peak_context_pct=peak_pct,
        rebilling_tokens=rebilling_tokens,
    )

    for seq, category, tokens in waste.tags:
        conn.execute(
            """
            UPDATE events SET waste_category = ?, waste_tokens = ?
            WHERE run_id = ? AND seq = ?
            """,
            (category, tokens, run_id, seq),
        )
    conn.execute(
        "UPDATE runs SET waste_tokens = ?, peak_context_pct = ? WHERE run_id = ?",
        (waste.total_waste_tokens, peak_pct, run_id),
    )
    conn.commit()
    _recompute_rollups(conn, run_id)
    _backfill_pillar_hooks(writer, run_id, events)


def _compute_rebilling(
    writer: CaptureWriter,
    run_id: str,
    *,
    events: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> int:
    """Pillar-1 re-billed stale tokens; writes context_regions (idempotent)."""
    from cairn.profile.compute import rebilling_for_run

    try:
        return rebilling_for_run(writer, run_id, events=events, model=model)
    except Exception:
        # Profiler must never break ingest/backfill.
        return 0


def _backfill_pillar_hooks(
    writer: CaptureWriter, run_id: str, events: list[dict[str, Any]]
) -> None:
    """Phase-B hooks for the pillar recomputations.

    Idempotent. Pillar-1 context_regions are written by ``_compute_rebilling``
    above; this hook recomputes fingerprints (Pillar 2) and outcomes (Pillar 3).
    """
    from cairn.metrics.fingerprint import backfill_fingerprint
    from cairn.outcomes import backfill_outcome

    conn = writer.connection
    with contextlib.suppress(Exception):
        backfill_fingerprint(writer, run_id, events=events)
    with contextlib.suppress(Exception):
        backfill_outcome(writer, run_id, events=events)
    try:
        from cairn.diagnose.engine import backfill_diagnostics, backfill_difficulty

        backfill_difficulty(writer, run_id, events=events)
        backfill_diagnostics(writer, run_id, events=events)
    except Exception:
        pass
    try:
        from cairn.optimize.memory import maybe_capture_episode

        maybe_capture_episode(writer, run_id, events=events)
    except Exception:
        pass
    conn.commit()


def backfill_ledger(root: Path) -> dict[str, int]:
    from cairn.ingest.writer import CaptureWriter

    writer = CaptureWriter(root)
    try:
        n = backfill_all(writer)
        recompute_rollups(writer, days=3650)
    finally:
        writer.close()
    return {"runs": n}


def _peak_context_pct(events: list[dict[str, Any]]) -> float | None:
    peak = 0
    window = 200_000
    for event in events:
        ctx = event.get("context_tokens_after")
        if ctx is not None and int(ctx) > 0:
            peak = max(peak, int(ctx))
    if peak <= 0:
        return None
    return round(peak / window * 100, 1)


def backfill_all(writer: CaptureWriter) -> int:
    rows = writer.connection.execute("SELECT run_id FROM runs").fetchall()
    for row in rows:
        backfill_run(writer, str(row["run_id"]))
    return len(rows)


def _recompute_rollups(conn: Any, run_id: str) -> None:
    run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None or not run["started_at"]:
        return
    day = str(run["started_at"])[:10]
    project = str(run["project"] or "")
    source = str(run["source"])
    model = str(run["model"] or "")

    conn.execute(
        """
        DELETE FROM rollup_daily
        WHERE day = ? AND project = ? AND source = ? AND model = ?
        """,
        (day, project, source, model),
    )

    row = conn.execute(
        """
        SELECT
          substr(started_at, 1, 10) AS day,
          COALESCE(project, '') AS project,
          source,
          COALESCE(model, '') AS model,
          COUNT(*) AS sessions,
          SUM(tool_call_count) AS tool_calls,
          SUM(tool_error_count) AS tool_errors,
          SUM(total_input_tokens) AS input_tokens,
          SUM(total_output_tokens) AS output_tokens,
          SUM(cache_read_tokens) AS cache_read_tokens,
          SUM(cache_creation_tokens) AS cache_creation_tokens,
          SUM(total_cost) AS cost_total,
          SUM(waste_tokens) AS waste_tokens,
          SUM(CASE WHEN has_cost = 1 THEN 1 ELSE 0 END) AS has_cost_sessions
        FROM runs
        WHERE substr(started_at, 1, 10) = ?
          AND COALESCE(project, '') = ?
          AND source = ?
          AND COALESCE(model, '') = ?
        GROUP BY day, project, source, model
        """,
        (day, project, source, model),
    ).fetchone()

    if row is None:
        conn.commit()
        return

    conn.execute(
        """
        INSERT INTO rollup_daily (
          day, project, source, model, sessions, tool_calls, tool_errors,
          input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
          cost_total, waste_tokens, has_cost_sessions
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["day"],
            row["project"],
            row["source"],
            row["model"],
            row["sessions"],
            row["tool_calls"],
            row["tool_errors"],
            row["input_tokens"],
            row["output_tokens"],
            row["cache_read_tokens"],
            row["cache_creation_tokens"],
            row["cost_total"],
            row["waste_tokens"],
            row["has_cost_sessions"],
        ),
    )
    conn.commit()


def recompute_rollups(writer: CaptureWriter, *, days: int = 90) -> None:
    """Rebuild rollup_daily from runs table."""
    conn = writer.connection
    conn.execute("DELETE FROM rollup_daily")
    rows = conn.execute(
        """
        SELECT
          substr(started_at, 1, 10) AS day,
          COALESCE(project, '') AS project,
          source,
          COALESCE(model, '') AS model,
          COUNT(*) AS sessions,
          SUM(tool_call_count) AS tool_calls,
          SUM(tool_error_count) AS tool_errors,
          SUM(total_input_tokens) AS input_tokens,
          SUM(total_output_tokens) AS output_tokens,
          SUM(cache_read_tokens) AS cache_read_tokens,
          SUM(cache_creation_tokens) AS cache_creation_tokens,
          SUM(total_cost) AS cost_total,
          SUM(waste_tokens) AS waste_tokens,
          SUM(CASE WHEN has_cost = 1 THEN 1 ELSE 0 END) AS has_cost_sessions
        FROM runs
        WHERE started_at >= date('now', ?)
        GROUP BY day, project, source, model
        """,
        (f"-{days} days",),
    ).fetchall()
    for r in rows:
        conn.execute(
            """
            INSERT INTO rollup_daily (
              day, project, source, model, sessions, tool_calls, tool_errors,
              input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
              cost_total, waste_tokens, has_cost_sessions
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(
                r[c]
                for c in (
                    "day",
                    "project",
                    "source",
                    "model",
                    "sessions",
                    "tool_calls",
                    "tool_errors",
                    "input_tokens",
                    "output_tokens",
                    "cache_read_tokens",
                    "cache_creation_tokens",
                    "cost_total",
                    "waste_tokens",
                    "has_cost_sessions",
                )
            ),
        )
    conn.commit()
