"""Build detector evaluation context from Cairn traces and spans."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Any


def build_context(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 14,
) -> dict[str, Any]:
    """Mirror legacy engine context using traces/spans tables."""
    since = f"-{days} days"
    runs = conn.execute(
        """
        SELECT trace_id, source, project, model, started_at, peak_context_pct,
               input_tokens, output_tokens, cost, cost_source,
               cache_read_tokens, cache_creation_tokens, context_window
        FROM traces
        WHERE workspace_id = ?
          AND (started_at IS NULL OR date(started_at) >= date('now', ?))
        ORDER BY started_at ASC
        """,
        (workspace_id, since),
    ).fetchall()

    total_tokens = 0
    total_cost = 0.0
    has_cost_sessions = 0
    high_context: list[dict[str, Any]] = []
    model_costs_30d: dict[str, float] = defaultdict(float)
    run_rows = list(runs)

    for r in run_rows:
        inp = int(r["input_tokens"] or 0)
        out = int(r["output_tokens"] or 0)
        total_tokens += inp + out
        if r["cost_source"] in ("observed", "priced"):
            has_cost_sessions += 1
            total_cost += float(r["cost"] or 0)
        pct = r["peak_context_pct"]
        if pct is not None and float(pct) >= 70:
            high_context.append({"run_id": str(r["trace_id"]), "peak_context_pct": float(pct)})

    model_rows = conn.execute(
        """
        SELECT model, SUM(cost) AS cost
        FROM traces
        WHERE workspace_id = ?
          AND date(started_at) >= date('now', '-30 days')
          AND cost_source IN ('observed', 'priced')
        GROUP BY model
        """,
        (workspace_id,),
    ).fetchall()
    for r in model_rows:
        if r["model"] and float(r["cost"] or 0) > 0:
            model_costs_30d[str(r["model"])] = float(r["cost"])

    waste_rows = conn.execute(
        """
        SELECT s.waste_category, COUNT(*) AS n, SUM(s.waste_tokens) AS tokens
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE s.waste_category IS NOT NULL
          AND t.workspace_id = ?
          AND date(t.started_at) >= date('now', ?)
        GROUP BY s.waste_category
        """,
        (workspace_id, since),
    ).fetchall()
    waste_by_cat: dict[str, dict[str, int]] = {}
    for row in waste_rows:
        waste_by_cat[str(row["waste_category"])] = {
            "events": int(row["n"]),
            "tokens": int(row["tokens"] or 0),
        }

    churn_rows = conn.execute(
        """
        SELECT s.path_rel, COUNT(*) AS n
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE s.kind = 'tool_call' AND s.name IN ('edit', 'write', 'multiedit')
          AND s.path_rel IS NOT NULL
          AND t.workspace_id = ?
          AND date(t.started_at) >= date('now', ?)
        GROUP BY s.path_rel
        HAVING n > 5
        """,
        (workspace_id, since),
    ).fetchall()
    file_churn = {str(r["path_rel"]): int(r["n"]) for r in churn_rows}

    rebilling = _rebilling_aggregate(conn, workspace_id=workspace_id, since=since)
    unused = _unused_tools(conn, workspace_id=workspace_id, days=days, since=since)
    retry_storm = _retry_storm_evidence(conn, workspace_id=workspace_id, since=since)
    thrash_files = _context_thrash_file_costs(conn, workspace_id=workspace_id, since=since)
    return {
        "days": days,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "has_cost_sessions": has_cost_sessions,
        "high_context_sessions": high_context,
        "identical_call_tokens": waste_by_cat.get("identical_call", {}).get("tokens", 0),
        "identical_call_events": waste_by_cat.get("identical_call", {}).get("events", 0),
        "oversize_result_tokens": waste_by_cat.get("oversize_result", {}).get("tokens", 0),
        "retry_loop_events": waste_by_cat.get("retry_loop", {}).get("events", 0),
        "stale_tool_result_events": waste_by_cat.get("stale_context", {}).get("events", 0),
        "stale_tool_result_tokens": waste_by_cat.get("stale_context", {}).get("tokens", 0),
        "file_churn": file_churn,
        "cache_stats_7d": _cache_stats(conn, workspace_id=workspace_id, days=7),
        "model_costs_30d": dict(model_costs_30d),
        "model_comparable_samples": _model_comparable_samples(conn, workspace_id=workspace_id),
        "runaway_sessions": _runaway_aggregate(conn, run_rows),
        "rebilling_tokens_14d": rebilling["tokens"],
        "rebilling_cost_14d": rebilling["cost"],
        "tool_schema_tokens": unused["schema_tokens"],
        "unused_tools": unused["tools"],
        "unused_tools_coverage": unused["coverage"],
        "retry_storm_attempts": retry_storm["attempts"],
        "retry_storm_cost_usd": retry_storm["cost_usd"],
        "retry_storm_span_ids": retry_storm["span_ids"],
        "context_thrash_file_costs": thrash_files,
        "context_thrash_span_ids": [
            item["span_id"] for item in thrash_files if item.get("span_id")
        ],
        "behavioral_drift": {"drift": False},
        "quality_regression": _quality_regression(conn, workspace_id),
        "subagent_heavy": _subagent_heavy(conn, run_rows),
        "failing_commands": _failing_commands(conn, workspace_id, days),
        "max_error_streak": _max_error_streak(conn, workspace_id, since),
        "cost_anomalies": _cost_anomalies(conn, workspace_id, since),
        "read_rereads": _read_rereads(conn, workspace_id, since),
    }


def _cache_stats(conn: sqlite3.Connection, *, workspace_id: str, days: int) -> dict[str, Any]:
    since = f"-{days} days"
    rows = conn.execute(
        """
        SELECT date(started_at) AS day, cache_read_tokens, cache_creation_tokens, trace_id
        FROM traces
        WHERE workspace_id = ?
          AND date(started_at) >= date('now', ?)
        """,
        (workspace_id, since),
    ).fetchall()
    if not rows:
        return {}
    total_read = 0
    total_creation = 0
    by_day: dict[str, dict[str, int]] = defaultdict(lambda: {"cache_read": 0, "cache_creation": 0})
    for r in rows:
        cr = int(r["cache_read_tokens"] or 0)
        cw = int(r["cache_creation_tokens"] or 0)
        total_read += cr
        total_creation += cw
        day = str(r["day"] or "unknown")
        by_day[day]["cache_read"] += cr
        by_day[day]["cache_creation"] += cw
    daily: list[dict[str, Any]] = []
    for day, v in sorted(by_day.items()):
        denom = v["cache_read"] + v["cache_creation"]
        daily.append(
            {
                "day": day,
                "cache_read": v["cache_read"],
                "cache_creation": v["cache_creation"],
                "hit_rate": round(v["cache_read"] / denom, 4) if denom > 0 else None,
            }
        )
    return {
        "cache_read": total_read,
        "cache_creation": total_creation,
        "daily": daily,
        "spike_count": 0,
    }


def _runaway_aggregate(
    conn: sqlite3.Connection, run_rows: list[sqlite3.Row]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in run_rows:
        rows = conn.execute(
            """
            SELECT seq, input_tokens
            FROM spans
            WHERE trace_id = ? AND kind = 'assistant_msg'
              AND input_tokens IS NOT NULL AND input_tokens > 0
            ORDER BY seq
            """,
            (str(r["trace_id"]),),
        ).fetchall()
        if len(rows) < 4:
            continue
        per_turn = [int(row["input_tokens"]) for row in rows]
        mid = len(per_turn) // 2
        first_avg = sum(per_turn[:mid]) / len(per_turn[:mid])
        second_avg = sum(per_turn[mid:]) / len(per_turn[mid:])
        if first_avg <= 0:
            continue
        ratio = second_avg / first_avg
        if ratio >= 3.0:
            out.append({"run_id": str(r["trace_id"]), "ratio": round(ratio, 2)})
    return out


def _quality_regression(conn: sqlite3.Connection, workspace_id: str) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT o.quality_score, t.trace_id
        FROM outcomes o
        JOIN traces t ON t.trace_id = o.trace_id
        WHERE t.workspace_id = ?
          AND o.quality_score IS NOT NULL
          AND date(t.started_at) >= date('now', '-14 days')
        ORDER BY t.started_at DESC
        LIMIT 20
        """,
        (workspace_id,),
    ).fetchall()
    if len(rows) < 4:
        return {"regressed": False}
    scores = [float(r["quality_score"]) for r in rows]
    recent = sum(scores[: len(scores) // 2]) / max(1, len(scores) // 2)
    older = sum(scores[len(scores) // 2 :]) / max(1, len(scores) - len(scores) // 2)
    return {
        "regressed": recent < older - 10,
        "recent_avg": round(recent, 1),
        "older_avg": round(older, 1),
    }


def _subagent_heavy(conn: sqlite3.Connection, run_rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in run_rows:
        trace_id = str(r["trace_id"])
        total = int(r["input_tokens"] or 0) + int(r["output_tokens"] or 0)
        if total <= 0:
            continue
        sub_rows = conn.execute(
            """
            SELECT SUM(COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0)) AS tok
            FROM spans WHERE trace_id = ? AND kind = 'subagent'
            """,
            (trace_id,),
        ).fetchone()
        sub_tok = int(sub_rows["tok"] or 0) if sub_rows else 0
        if sub_tok <= 0:
            continue
        share = sub_tok / total
        if share < 0.4:
            continue
        outcome = conn.execute(
            "SELECT quality_score FROM outcomes WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        quality = float(outcome["quality_score"]) if outcome and outcome["quality_score"] else None
        if quality is not None and quality >= 60:
            continue
        out.append(
            {
                "run_id": trace_id,
                "share_pct": round(share * 100, 1),
                "subagent_tokens": sub_tok,
            }
        )
    return out


def _failing_commands(
    conn: sqlite3.Connection, workspace_id: str, days: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.name, COUNT(*) AS failures
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE s.status = 'error' AND s.name IS NOT NULL
          AND t.workspace_id = ?
          AND date(t.started_at) >= date('now', ?)
        GROUP BY s.name
        HAVING failures >= 3
        ORDER BY failures DESC
        LIMIT 10
        """,
        (workspace_id, f"-{days} days"),
    ).fetchall()
    return [{"name": str(r["name"]), "failures": int(r["failures"])} for r in rows]


def _max_error_streak(conn: sqlite3.Connection, workspace_id: str, since: str) -> int:
    trace_rows = conn.execute(
        """
        SELECT trace_id FROM traces
        WHERE workspace_id = ?
          AND (started_at IS NULL OR date(started_at) >= date('now', ?))
        """,
        (workspace_id, since),
    ).fetchall()
    max_streak = 0
    for row in trace_rows:
        spans = conn.execute(
            """
            SELECT status FROM spans
            WHERE trace_id = ?
            ORDER BY seq
            """,
            (str(row["trace_id"]),),
        ).fetchall()
        streak = 0
        for span in spans:
            if str(span["status"]) == "error":
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
    return max_streak


def _cost_anomalies(
    conn: sqlite3.Connection, workspace_id: str, since: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT trace_id, cost, difficulty
        FROM traces
        WHERE workspace_id = ?
          AND cost > 0
          AND (started_at IS NULL OR date(started_at) >= date('now', ?))
        """,
        (workspace_id, since),
    ).fetchall()
    by_bucket: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in rows:
        bucket = str(row["difficulty"] if row["difficulty"] is not None else "unknown")
        by_bucket[bucket].append((str(row["trace_id"]), float(row["cost"] or 0.0)))

    anomalies: list[dict[str, Any]] = []
    for items in by_bucket.values():
        if len(items) < 20:
            continue
        costs = [cost for _, cost in items]
        mean = sum(costs) / len(costs)
        variance = sum((c - mean) ** 2 for c in costs) / max(len(costs) - 1, 1)
        std = variance**0.5
        threshold = mean + 3.0 * std
        for trace_id, cost in items:
            if cost > threshold:
                anomalies.append(
                    {
                        "trace_id": trace_id,
                        "cost": cost,
                        "threshold": round(threshold, 4),
                    }
                )
    anomalies.sort(key=lambda item: float(item["cost"]), reverse=True)
    return anomalies[:5]


def _read_rereads(conn: sqlite3.Connection, workspace_id: str, since: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.path_rel, COALESCE(s.text_hash, s.args_hash) AS content_hash, COUNT(*) AS n
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE s.name = 'read'
          AND s.path_rel IS NOT NULL
          AND COALESCE(s.text_hash, s.args_hash) IS NOT NULL
          AND t.workspace_id = ?
          AND (t.started_at IS NULL OR date(t.started_at) >= date('now', ?))
        GROUP BY s.path_rel, content_hash
        HAVING n >= 3
        ORDER BY n DESC
        LIMIT 10
        """,
        (workspace_id, since),
    ).fetchall()
    return [
        {
            "path": str(r["path_rel"]),
            "content_hash": str(r["content_hash"]),
            "reads": int(r["n"]),
        }
        for r in rows
    ]


def _rebilling_aggregate(
    conn: sqlite3.Connection, *, workspace_id: str, since: str
) -> dict[str, float | int]:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(tokens - largest), 0) AS tokens,
               COALESCE(SUM(cost - largest_cost), 0) AS cost
        FROM (
          SELECT SUM(cr.tokens) AS tokens,
                 MAX(cr.tokens) AS largest,
                 SUM(cr.cost) AS cost,
                 MAX(cr.cost) AS largest_cost
          FROM context_regions cr
          JOIN spans s ON s.span_id = cr.span_id
          JOIN traces t ON t.trace_id = s.trace_id
          WHERE t.workspace_id = ?
            AND (t.started_at IS NULL OR date(t.started_at) >= date('now', ?))
            AND cr.content_hash IS NOT NULL AND cr.content_hash != ''
          GROUP BY cr.content_hash, cr.region
          HAVING COUNT(*) > 1
        )
        """,
        (workspace_id, since),
    ).fetchone()
    return {
        "tokens": int(row["tokens"] or 0) if row else 0,
        "cost": float(row["cost"] or 0.0) if row else 0.0,
    }


def _unused_tools(
    conn: sqlite3.Connection, *, workspace_id: str, days: int, since: str
) -> dict[str, Any]:
    schema_row = conn.execute(
        """
        SELECT COALESCE(SUM(cr.tokens), 0) AS tokens,
               COUNT(DISTINCT t.trace_id) AS sessions,
               COUNT(DISTINCT s.span_id) AS turns
        FROM context_regions cr
        JOIN spans s ON s.span_id = cr.span_id
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ?
          AND (t.started_at IS NULL OR date(t.started_at) >= date('now', ?))
          AND cr.region = 'tool_schema'
        """,
        (workspace_id, since),
    ).fetchone()
    schema_tokens = int(schema_row["tokens"] or 0) if schema_row else 0
    sessions = int(schema_row["sessions"] or 0) if schema_row else 0
    turns = int(schema_row["turns"] or 0) if schema_row else 0
    if schema_tokens <= 0:
        return {"tools": [], "schema_tokens": 0, "coverage": "No tool_schema region tokens."}

    called_now = {
        str(row["name"])
        for row in conn.execute(
            """
            SELECT DISTINCT s.name
            FROM spans s
            JOIN traces t ON t.trace_id = s.trace_id
            WHERE t.workspace_id = ?
              AND (t.started_at IS NULL OR date(t.started_at) >= date('now', ?))
              AND s.kind = 'tool_call' AND s.name IS NOT NULL AND s.name != ''
            """,
            (workspace_id, since),
        ).fetchall()
    }
    historical = {
        str(row["name"])
        for row in conn.execute(
            """
            SELECT DISTINCT s.name
            FROM spans s
            JOIN traces t ON t.trace_id = s.trace_id
            WHERE t.workspace_id = ?
              AND date(t.started_at) >= date('now', '-90 days')
              AND s.kind = 'tool_call' AND s.name IS NOT NULL AND s.name != ''
            """,
            (workspace_id,),
        ).fetchall()
    }
    unused_names = sorted(historical - called_now)
    tokens_per_turn = max(1, schema_tokens // max(1, turns))
    tools: list[dict[str, Any]] = []
    for name in unused_names[:5]:
        tools.append(
            {
                "tool": name,
                "total_turns": max(turns, days),
                "tokens_per_turn": tokens_per_turn,
                "sessions": sessions,
            }
        )
    if not tools and schema_tokens >= 2_000 and sessions >= 3:
        tools.append(
            {
                "tool": "(unattributed-schema)",
                "total_turns": max(turns, days),
                "tokens_per_turn": tokens_per_turn,
                "sessions": sessions,
            }
        )
        coverage = (
            "Schema tokens are present but unused tool names could not be linked; "
            "estimate stays unpriced."
        )
    elif tools:
        coverage = (
            "Unused names are historical tools with zero calls in-window while tool_schema "
            "tokens continue; provider schema packaging may differ."
        )
    else:
        coverage = "No unused tool names under the historical-vs-window heuristic."
    return {"tools": tools, "schema_tokens": schema_tokens, "coverage": coverage}


def _retry_storm_evidence(
    conn: sqlite3.Connection, *, workspace_id: str, since: str
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT s.span_id, s.waste_tokens, t.cost, t.input_tokens, t.output_tokens
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ?
          AND (t.started_at IS NULL OR date(t.started_at) >= date('now', ?))
          AND s.waste_category IN ('retry_loop', 'blind_retry', 'identical_call')
        ORDER BY s.waste_tokens DESC
        LIMIT 40
        """,
        (workspace_id, since),
    ).fetchall()
    span_ids = [str(row["span_id"]) for row in rows[:12]]
    attempts = len(rows)
    cost_usd = 0.0
    for row in rows:
        waste = int(row["waste_tokens"] or 0)
        total_tokens = int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0)
        session_cost = float(row["cost"] or 0.0)
        if waste > 0 and total_tokens > 0 and session_cost > 0:
            cost_usd += session_cost * (waste / total_tokens)
    return {
        "attempts": attempts,
        "cost_usd": round(cost_usd, 4),
        "span_ids": span_ids,
    }


def _context_thrash_file_costs(
    conn: sqlite3.Connection, *, workspace_id: str, since: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.path_rel,
               SUM(COALESCE(s.waste_tokens, 0)) AS waste_tokens,
               COUNT(*) AS events,
               MIN(s.span_id) AS sample_span
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ?
          AND (t.started_at IS NULL OR date(t.started_at) >= date('now', ?))
          AND s.path_rel IS NOT NULL
          AND s.waste_category IN ('identical_call', 'stale_context', 're_read')
        GROUP BY s.path_rel
        ORDER BY waste_tokens DESC
        LIMIT 8
        """,
        (workspace_id, since),
    ).fetchall()
    return [
        {
            "path": str(row["path_rel"]),
            "waste_tokens": int(row["waste_tokens"] or 0),
            "events": int(row["events"] or 0),
            "span_id": str(row["sample_span"]),
        }
        for row in rows
    ]


def _model_comparable_samples(conn: sqlite3.Connection, *, workspace_id: str) -> int:
    """Count sessions that share difficulty bands across ≥2 priced models."""
    rows = conn.execute(
        """
        SELECT difficulty, COUNT(DISTINCT model) AS models, COUNT(*) AS n
        FROM traces
        WHERE workspace_id = ?
          AND date(started_at) >= date('now', '-30 days')
          AND cost_source IN ('observed', 'priced')
          AND model IS NOT NULL AND model != ''
          AND difficulty IS NOT NULL
        GROUP BY difficulty
        HAVING models >= 2 AND n >= 2
        """,
        (workspace_id,),
    ).fetchall()
    return sum(int(row["n"] or 0) for row in rows)
