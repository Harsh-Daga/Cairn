"""Build detector evaluation context from v4 traces/spans."""

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
        "runaway_sessions": _runaway_aggregate(conn, run_rows),
        "rebilling_tokens_14d": 0,
        "rebilling_cost_14d": 0.0,
        "unused_tools": [],
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
