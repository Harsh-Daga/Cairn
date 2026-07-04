"""Build JSON payloads for dashboard API endpoints."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal


def _since_date(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")


def _primary_project(conn: sqlite3.Connection, *, since: str) -> str | None:
    row = conn.execute(
        """
        SELECT project, COUNT(*) AS n
        FROM runs
        WHERE started_at >= ? AND project IS NOT NULL AND project != ''
        GROUP BY project
        ORDER BY n DESC
        LIMIT 1
        """,
        (since,),
    ).fetchone()
    if row is None:
        return None
    return str(row["project"])


def _data_notes(conn: sqlite3.Connection, *, since: str) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []

    # Cursor: distinguish best-of-N subcomposers from sessions missing token data.
    cursor_sub = conn.execute(
        """
        SELECT COUNT(*) AS n FROM runs
        WHERE started_at >= ? AND source = 'cursor' AND status = 'best-of-n-subagent'
        """,
        (since,),
    ).fetchone()
    sub_n = int(cursor_sub["n"] or 0) if cursor_sub else 0
    if sub_n:
        notes.append(
            {
                "source": "cursor",
                "sessions": sub_n,
                "issue": "best_of_n_subcomposer",
                "message": (
                    f"{sub_n} Cursor best-of-N subcomposer run(s) excluded from spend totals "
                    f"to avoid double-counting parent composer cost."
                ),
            }
        )

    cursor_no_tokens = conn.execute(
        """
        SELECT COUNT(*) AS n FROM runs
        WHERE started_at >= ? AND source = 'cursor' AND has_cost = 0
          AND status != 'best-of-n-subagent'
          AND total_input_tokens = 0 AND total_output_tokens = 0
        """,
        (since,),
    ).fetchone()
    no_tok_n = int(cursor_no_tokens["n"] or 0) if cursor_no_tokens else 0
    if no_tok_n:
        notes.append(
            {
                "source": "cursor",
                "sessions": no_tok_n,
                "issue": "no_token_data",
                "message": (
                    f"{no_tok_n} Cursor session(s) have no tokenCount/costInCents in state.vscdb "
                    f"(older Cursor builds or privacy mode)."
                ),
                "help_url": "https://github.com/Harsh-Daga/Cairn#cursor-support",
            }
        )

    rows = conn.execute(
        """
        SELECT source, COUNT(*) AS n
        FROM runs
        WHERE started_at >= ? AND has_cost = 0 AND source != 'cursor'
        GROUP BY source
        """,
        (since,),
    ).fetchall()
    for r in rows:
        source = str(r["source"])
        n = int(r["n"])
        notes.append(
            {
                "source": source,
                "sessions": n,
                "issue": "no_cost_data",
                "message": f"{n} {source} session(s) have no reliable cost/token data.",
            }
        )

    cursor_other = conn.execute(
        """
        SELECT COUNT(*) AS n FROM runs
        WHERE started_at >= ? AND source = 'cursor' AND has_cost = 0
          AND status != 'best-of-n-subagent'
          AND (total_input_tokens > 0 OR total_output_tokens > 0)
        """,
        (since,),
    ).fetchone()
    other_n = int(cursor_other["n"] or 0) if cursor_other else 0
    if other_n:
        notes.append(
            {
                "source": "cursor",
                "sessions": other_n,
                "issue": "cost_unavailable",
                "message": (
                    f"{other_n} Cursor session(s) recorded tokens but no billable cost "
                    f"(missing costInCents in usageData)."
                ),
            }
        )
    return notes


def overview_payload(
    conn: sqlite3.Connection,
    *,
    days: int = 30,
    project: str | None = None,
    source: str | None = None,
    repo_name: str | None = None,
) -> dict[str, Any]:
    since = _since_date(days)
    clauses = ["started_at >= ?"]
    params: list[Any] = [since]
    if project:
        clauses.append("project = ?")
        params.append(project)
    if source:
        clauses.append("source = ?")
        params.append(source)
    where = " AND ".join(clauses)

    row = conn.execute(
        f"""
        SELECT
          COUNT(*) AS sessions,
          SUM(total_cost) AS total_cost,
          SUM(CASE WHEN has_cost = 1 THEN 1 ELSE 0 END) AS has_cost_sessions,
          SUM(CASE WHEN has_cost = 0 THEN 1 ELSE 0 END) AS estimated_sessions,
          SUM(total_input_tokens + total_output_tokens) AS total_tokens,
          SUM(waste_tokens) AS waste_tokens,
          SUM(tool_call_count) AS tool_calls,
          SUM(tool_error_count) AS tool_errors
        FROM runs WHERE {where}
        """,
        params,
    ).fetchone()

    sessions = int(row["sessions"] or 0)
    total_tokens = int(row["total_tokens"] or 0)
    waste_tokens = int(row["waste_tokens"] or 0)
    tool_calls = int(row["tool_calls"] or 0)
    tool_errors = int(row["tool_errors"] or 0)
    total_cost = float(row["total_cost"] or 0)
    waste_pct = (waste_tokens / total_tokens * 100) if total_tokens else 0.0
    waste_display: str | float
    if waste_tokens and waste_pct < 0.01:
        waste_display = "<0.01"
    elif waste_pct < 1:
        waste_display = round(waste_pct, 2)
    else:
        waste_display = round(waste_pct, 1)
    tool_error_pct = (tool_errors / tool_calls * 100) if tool_calls else 0.0

    by_source_rows = conn.execute(
        f"""
        SELECT source, COUNT(*) AS sessions, SUM(total_cost) AS cost,
               SUM(total_input_tokens + total_output_tokens) AS tokens
        FROM runs WHERE {where}
        GROUP BY source ORDER BY sessions DESC
        """,
        params,
    ).fetchall()
    by_source = [
        {
            "source": str(r["source"]),
            "sessions": int(r["sessions"]),
            "cost": float(r["cost"] or 0),
            "tokens": int(r["tokens"] or 0),
        }
        for r in by_source_rows
    ]

    prev_since = _since_date(days * 2)
    prev = conn.execute(
        """
        SELECT COUNT(*) AS sessions, SUM(total_cost) AS cost,
               SUM(total_input_tokens + total_output_tokens) AS tokens
        FROM runs WHERE started_at >= ? AND started_at < ?
        """,
        (prev_since, since),
    ).fetchone()

    diag_summary = _diagnostics_summary(conn, since=since)
    confidence = _aggregate_confidence(conn, since=since)
    payload_base = {
        "summary": {
            "sessions": sessions,
            "total_cost": round(total_cost, 2),
            "has_cost_sessions": int(row["has_cost_sessions"] or 0),
            "estimated_sessions": int(row["estimated_sessions"] or 0),
            "total_tokens": total_tokens,
            "waste_tokens": waste_tokens,
            "waste_pct": waste_display,
            "tool_error_pct": round(tool_error_pct, 1),
        },
        "project_name": repo_name or project or _primary_project(conn, since=since),
        "by_source": by_source,
        "kpis": {
            "spend": round(total_cost, 2),
            "tokens": total_tokens,
            "waste_tokens": waste_tokens,
            "waste_pct": waste_display,
            "sessions": sessions,
            "tool_errors_pct": round(tool_error_pct, 1),
        },
        "previous_period": {
            "sessions": int(prev["sessions"] or 0),
            "total_cost": float(prev["cost"] or 0),
            "total_tokens": int(prev["tokens"] or 0),
        },
        "diagnostics_summary": diag_summary,
        "confidence": confidence,
        "data_notes": _data_notes(conn, since=since),
    }
    from cairn.render.narrative import overview_narrative

    narrative = overview_narrative(
        {
            "spend": total_cost if int(row["has_cost_sessions"] or 0) else None,
            "waste": {"pct": waste_display if total_tokens else None},
            "sessions_count": sessions,
            "diagnostics_summary": diag_summary,
            "optimization_ready": False,
        }
    )
    payload_base["narrative"] = narrative
    return payload_base


def _diagnostics_summary(conn: sqlite3.Connection, *, since: str) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
          SUM(
            CASE WHEN d.outcome_label IS NOT NULL AND d.outcome_label != 'landed'
            THEN 1 ELSE 0 END
          ) AS failed,
          SUM(CASE WHEN d.cascade_root_event_id IS NOT NULL THEN 1 ELSE 0 END) AS cascades
        FROM diagnostics d
        JOIN runs r ON r.run_id = d.run_id
        WHERE r.started_at >= ?
        """,
        (since,),
    ).fetchone()
    return {
        "failed_sessions": int(row["failed"] or 0) if row else 0,
        "cascade_sessions": int(row["cascades"] or 0) if row else 0,
    }


def _aggregate_confidence(conn: sqlite3.Connection, *, since: str) -> dict[str, Any]:
    """Roll up data_quality provenance for headline KPI chips."""
    row = conn.execute(
        """
        SELECT
          AVG(dq.pct_tokens_measured) AS avg_measured,
          AVG(dq.pct_tokens_estimated) AS avg_estimated,
          MIN(dq.cost_source) AS cost_source
        FROM data_quality dq
        JOIN runs r ON r.run_id = dq.run_id
        WHERE r.started_at >= ?
        """,
        (since,),
    ).fetchone()
    avg_estimated = float(row["avg_estimated"] or 0) if row else 0.0
    cost_source = str(row["cost_source"] or "absent") if row else "absent"
    from cairn.ingest.tokenize import estimation_error_pct

    if avg_estimated <= 0 and cost_source in ("observed", "priced"):
        return {
            "estimation_method": "exact",
            "estimation_error_pct": None,
            "pct_tokens_measured": float(row["avg_measured"])
            if row and row["avg_measured"]
            else None,
            "cost_source": cost_source,
        }
    method: Literal["exact", "tiktoken", "heuristic"] = (
        "heuristic" if avg_estimated > 0 else "exact"
    )
    err = estimation_error_pct(method, calibrated=avg_estimated > 0) if method != "exact" else None
    return {
        "estimation_method": method,
        "estimation_error_pct": err,
        "pct_tokens_measured": float(row["avg_measured"])
        if row and row["avg_measured"] is not None
        else None,
        "cost_source": cost_source,
    }


def charts_payload(
    conn: sqlite3.Connection,
    *,
    days: int = 30,
    project: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    since = _since_date(days)
    clauses = ["day >= ?"]
    params: list[Any] = [since]
    if project:
        clauses.append("project = ?")
        params.append(project)
    if source:
        clauses.append("source = ?")
        params.append(source)
    where = " AND ".join(clauses)

    daily_cost_map: dict[str, dict[str, float]] = defaultdict(dict)
    daily_tokens: list[dict[str, Any]] = []
    for r in conn.execute(
        f"""
        SELECT day, model, SUM(cost_total) AS cost,
               SUM(input_tokens) AS input, SUM(output_tokens) AS output,
               SUM(cache_read_tokens) AS cache_read
        FROM rollup_daily WHERE {where}
        GROUP BY day, model ORDER BY day
        """,
        params,
    ).fetchall():
        day = str(r["day"])
        model = str(r["model"] or "unknown")
        daily_cost_map[day][model] = daily_cost_map[day].get(model, 0) + float(r["cost"] or 0)

    tokens_by_day: dict[str, dict[str, int]] = defaultdict(
        lambda: {"input": 0, "output": 0, "cache_read": 0}
    )
    for r in conn.execute(
        f"""
        SELECT day, SUM(input_tokens) AS input, SUM(output_tokens) AS output,
               SUM(cache_read_tokens) AS cache_read
        FROM rollup_daily WHERE {where}
        GROUP BY day ORDER BY day
        """,
        params,
    ).fetchall():
        day = str(r["day"])
        tokens_by_day[day] = {
            "input": int(r["input"] or 0),
            "output": int(r["output"] or 0),
            "cache_read": int(r["cache_read"] or 0),
        }

    daily_cost = [{"day": d, "by_model": models} for d, models in sorted(daily_cost_map.items())]
    daily_tokens = [{"day": d, **tokens_by_day[d]} for d in sorted(tokens_by_day)]

    waste_rows = conn.execute(
        """
        SELECT e.waste_category, COUNT(*) AS n, SUM(e.waste_tokens) AS tokens
        FROM events e
        JOIN runs r ON r.run_id = e.run_id
        WHERE e.waste_category IS NOT NULL AND r.started_at >= ?
        GROUP BY e.waste_category
        """,
        (since,),
    ).fetchall()
    waste_by_category: dict[str, Any] = {}
    for r in waste_rows:
        cat = str(r["waste_category"])
        waste_by_category[cat] = {
            "tokens": int(r["tokens"] or 0),
            "events": int(r["n"]),
        }
    # Run-level waste not tied to per-event categories (e.g. rebilling).
    run_waste = conn.execute(
        """
        SELECT SUM(waste_tokens) AS tokens
        FROM runs
        WHERE started_at >= ? AND waste_tokens > 0
        """,
        (since,),
    ).fetchone()
    tagged_tokens = sum(int(v["tokens"]) for v in waste_by_category.values())
    run_total = int(run_waste["tokens"] or 0) if run_waste else 0
    if run_total > tagged_tokens:
        waste_by_category.setdefault(
            "other",
            {"tokens": run_total - tagged_tokens, "events": 0},
        )

    context_rows = conn.execute(
        """
        SELECT substr(started_at, 1, 10) AS day, AVG(peak_context_pct) AS mean_peak_pct
        FROM runs
        WHERE peak_context_pct IS NOT NULL AND started_at >= ?
        GROUP BY day ORDER BY day
        """,
        (since,),
    ).fetchall()
    if not context_rows:
        context_rows = conn.execute(
            """
            WITH turn_totals AS (
              SELECT e.run_id, cr.last_seen_turn AS turn, SUM(cr.tokens) AS turn_tokens
              FROM context_regions cr
              JOIN events e ON e.event_id = cr.event_id
              GROUP BY e.run_id, cr.last_seen_turn
            ),
            run_peaks AS (
              SELECT run_id, MAX(turn_tokens) AS peak_tokens
              FROM turn_totals
              GROUP BY run_id
            )
            SELECT substr(r.started_at, 1, 10) AS day,
                   AVG(
                     rp.peak_tokens * 100.0
                     / COALESCE(NULLIF(r.context_window, 0), 200000)
                   ) AS mean_peak_pct
            FROM run_peaks rp
            JOIN runs r ON r.run_id = rp.run_id
            WHERE r.started_at >= ?
            GROUP BY day ORDER BY day
            """,
            (since,),
        ).fetchall()
    context_pressure = [
        {"day": str(r["day"]), "mean_peak_pct": round(float(r["mean_peak_pct"]), 1)}
        for r in context_rows
    ]

    return {
        "daily_cost": daily_cost,
        "daily_tokens": daily_tokens,
        "waste_by_category": waste_by_category,
        "context_pressure": context_pressure,
    }


def sessions_payload(
    conn: sqlite3.Connection,
    *,
    days: int = 30,
    project: str | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    since = _since_date(days)
    clauses = ["started_at >= ?"]
    params: list[Any] = [since]
    if project:
        clauses.append("project = ?")
        params.append(project)
    if source:
        clauses.append("source = ?")
        params.append(source)
    where = " AND ".join(clauses)

    total = conn.execute(f"SELECT COUNT(*) FROM runs WHERE {where}", params).fetchone()
    rows = conn.execute(
        f"""
        SELECT run_id, source, model, started_at, project, event_count,
               total_input_tokens, total_output_tokens, cache_read_tokens,
               total_cost, has_cost,
               waste_tokens, tool_error_count, status
        FROM runs WHERE {where}
        ORDER BY started_at DESC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()

    sessions = []
    for r in rows:
        has_cost = bool(r["has_cost"])
        sessions.append(
            {
                "run_id": str(r["run_id"]),
                "source": str(r["source"]),
                "model": r["model"],
                "started_at": r["started_at"],
                "project": r["project"],
                "turns": _turn_count(conn, str(r["run_id"])),
                "event_count": int(r["event_count"] or 0),
                "input_tokens": int(r["total_input_tokens"]) if has_cost else None,
                "output_tokens": int(r["total_output_tokens"]) if has_cost else None,
                "cache_read_tokens": int(r["cache_read_tokens"] or 0) if has_cost else None,
                "total_cost": float(r["total_cost"]) if has_cost else None,
                "has_cost": has_cost,
                "waste_tokens": int(r["waste_tokens"] or 0),
                "tool_errors": int(r["tool_error_count"] or 0),
                "status": str(r["status"]),
            }
        )
    return {"sessions": sessions, "total": int(total[0]) if total else 0}


def _turn_count(conn: sqlite3.Connection, run_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM events WHERE run_id = ? AND type = 'user_prompt'",
        (run_id,),
    ).fetchone()
    user_turns = int(row[0]) if row else 0
    if user_turns:
        return user_turns
    row = conn.execute(
        "SELECT event_count FROM runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    return int(row[0] or 0) if row else 0


def search_payload(
    conn: sqlite3.Connection,
    *,
    q: str,
    limit: int = 20,
) -> dict[str, Any]:
    if not q.strip():
        return {"results": [], "fts_available": True}
    try:
        rows = conn.execute(
            """
            SELECT f.run_id, f.seq, f.text_inline, r.source, r.started_at,
                   r.total_cost, r.has_cost
            FROM events_fts f
            JOIN runs r ON r.run_id = f.run_id
            WHERE events_fts MATCH ?
            LIMIT ?
            """,
            (q, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            """
            SELECT e.run_id, e.seq, e.text_inline, r.source, r.started_at,
                   r.total_cost, r.has_cost
            FROM events e
            JOIN runs r ON r.run_id = e.run_id
            WHERE e.text_inline LIKE ?
            LIMIT ?
            """,
            (f"%{q}%", limit),
        ).fetchall()

    results = []
    for r in rows:
        results.append(
            {
                "run_id": str(r["run_id"]),
                "seq": int(r["seq"]),
                "excerpt": (r["text_inline"] or "")[:200],
                "source": str(r["source"]),
                "started_at": r["started_at"],
                "cost": float(r["total_cost"]) if r["has_cost"] else None,
            }
        )
    return {"results": results, "fts_available": True}


def optimize_payload(conn: sqlite3.Connection, *, root: Path | None = None) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT opt_id, created_at, target_file, block_key, kind, content,
               evidence_json, status, applied_at, baseline_metric, baseline_sessions,
               outcome_metric, outcome_sessions, measured_at,
               fingerprint_distance_baseline, fingerprint_distance_outcome
        FROM optimizations ORDER BY created_at DESC
        """
    ).fetchall()
    opts = []
    for r in rows:
        opts.append(
            {
                "opt_id": str(r["opt_id"]),
                "created_at": r["created_at"],
                "target_file": r["target_file"],
                "entry_id": r["block_key"],
                "kind": r["kind"],
                "content": r["content"],
                "evidence_json": r["evidence_json"],
                "status": r["status"],
                "applied_at": r["applied_at"],
                "baseline_metric": r["baseline_metric"],
                "baseline_sessions": r["baseline_sessions"],
                "outcome_metric": r["outcome_metric"],
                "outcome_sessions": r["outcome_sessions"],
                "measured_at": r["measured_at"],
                "fingerprint_distance_baseline": r["fingerprint_distance_baseline"],
                "fingerprint_distance_outcome": r["fingerprint_distance_outcome"],
            }
        )
    patterns = _detect_patterns(conn)
    payload: dict[str, Any] = {
        "optimizations": opts,
        "has_run": len(opts) > 0,
        "patterns": patterns,
        "session_count": conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
    }
    # Pre-run proposals (dry-run) + post-run measurement state, when a root is
    # available (the live server passes one; the SSE path omits it).
    if root is not None:
        try:
            from cairn.optimize.engine import generate_proposals

            records = generate_proposals(conn, root, days=14)
            payload["proposals"] = [
                {
                    "kind": r.entry.kind,
                    "entry_id": r.entry.entry_id,
                    "content": r.entry.content,
                    "candidates": r.candidates,
                    "selected_index": r.selected_index,
                    "confidence": r.entry.confidence,
                    "evidence": r.evidence,
                }
                for r in records
            ]
        except Exception:
            payload["proposals"] = []
        payload["measurement"] = _measurement_state(opts)
    return payload


def _measurement_state(opts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for o in opts:
        if o.get("status") not in ("applied", "pruned"):
            continue
        baseline = o.get("baseline_metric")
        outcome = o.get("outcome_metric")
        fpb = o.get("fingerprint_distance_baseline")
        fpo = o.get("fingerprint_distance_outcome")
        out.append(
            {
                "entry_id": o["entry_id"],
                "status": o["status"],
                "baseline": baseline,
                "outcome": outcome,
                "fingerprint_distance_baseline": fpb,
                "fingerprint_distance_outcome": fpo,
                "outcome_sessions": o.get("outcome_sessions"),
            }
        )
    return out


def _detect_patterns(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    grep_row = conn.execute(
        """
        SELECT text_inline, COUNT(*) AS n, COUNT(DISTINCT run_id) AS sessions
        FROM events
        WHERE tool_norm_name = 'search' AND text_inline IS NOT NULL
          AND run_id IN (SELECT run_id FROM runs WHERE started_at >= date('now', '-14 days'))
        GROUP BY text_hash HAVING n >= 3
        ORDER BY n DESC LIMIT 1
        """
    ).fetchone()
    if grep_row:
        patterns.append(
            {
                "kind": "identical_grep",
                "text": f"{int(grep_row['n'])} identical grep/search calls across sessions",
                "detail": (grep_row["text_inline"] or "")[:60],
            }
        )
    read_row = conn.execute(
        """
        SELECT path_rel, COUNT(*) AS n
        FROM events
        WHERE tool_norm_name = 'read' AND path_rel IS NOT NULL
          AND run_id IN (SELECT run_id FROM runs WHERE started_at >= date('now', '-14 days'))
        GROUP BY path_rel HAVING n >= 3
        ORDER BY n DESC LIMIT 1
        """
    ).fetchone()
    if read_row:
        patterns.append(
            {
                "kind": "repeated_reads",
                "text": f"{read_row['path_rel']} read {int(read_row['n'])} times",
            }
        )
    ctx_row = conn.execute(
        """
        SELECT COUNT(*) FROM runs
        WHERE peak_context_pct > 85 AND started_at >= date('now', '-14 days')
        """
    ).fetchone()
    if ctx_row and int(ctx_row[0]) > 0:
        patterns.append(
            {
                "kind": "context_overflow",
                "text": f"{int(ctx_row[0])} sessions exceeded 85% context window",
            }
        )
    return patterns


def top_files_payload(conn: sqlite3.Connection, *, days: int = 14) -> dict[str, Any]:
    since = _since_date(days)
    rows = conn.execute(
        """
        SELECT e.path_rel,
               SUM(CASE WHEN e.tool_norm_name = 'read' THEN 1 ELSE 0 END) AS reads,
               SUM(CASE WHEN e.tool_norm_name = 'edit' THEN 1 ELSE 0 END) AS edits,
               CAST(SUM(
                 CASE WHEN e.type = 'tool_call' AND r.event_count > 0
                 THEN (r.total_input_tokens + r.total_output_tokens) * 1.0 / r.event_count
                 ELSE 0 END
               ) AS INTEGER) AS tokens
        FROM events e
        JOIN runs r ON r.run_id = e.run_id
        WHERE e.path_rel IS NOT NULL AND r.started_at >= ? AND r.has_cost = 1
        GROUP BY e.path_rel
        ORDER BY tokens DESC
        LIMIT 20
        """,
        (since,),
    ).fetchall()
    files = [
        {
            "path": str(r["path_rel"]),
            "reads": int(r["reads"]),
            "edits": int(r["edits"]),
            "tokens": int(r["tokens"]),
            "cost": round(int(r["tokens"]) / 1_000_000 * 3.0, 4),
        }
        for r in rows
    ]
    no_cost_rows = conn.execute(
        """
        SELECT e.path_rel,
               SUM(CASE WHEN e.tool_norm_name = 'read' THEN 1 ELSE 0 END) AS reads,
               SUM(CASE WHEN e.tool_norm_name = 'edit' THEN 1 ELSE 0 END) AS edits
        FROM events e
        JOIN runs r ON r.run_id = e.run_id
        WHERE e.path_rel IS NOT NULL AND r.started_at >= ? AND r.has_cost = 0
        GROUP BY e.path_rel
        ORDER BY reads + edits DESC
        LIMIT 10
        """,
        (since,),
    ).fetchall()
    for r in no_cost_rows:
        files.append(
            {
                "path": str(r["path_rel"]),
                "reads": int(r["reads"]),
                "edits": int(r["edits"]),
                "tokens": None,
                "cost": None,
            }
        )
    return {"files": files}
