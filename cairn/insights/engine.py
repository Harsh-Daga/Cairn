"""Insight evaluation engine — v3 ledger queries."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from cairn.insights.rules import ALL_RULES, Insight
from cairn.ledger.ledger import Ledger


def evaluate(ledger: Ledger, *, days: int = 14) -> list[Insight]:
    ctx = _build_context(ledger.connection, days=days)
    insights: list[Insight] = []
    for rule in ALL_RULES:
        result = rule(ctx)
        if result is not None:
            insights.append(result)
    severity_order = {"error": 0, "warning": 1, "info": 2, "suggestion": 3}
    insights.sort(key=lambda i: (severity_order.get(i.severity, 4), -(i.savings_estimate or 0)))
    return insights


def _build_context(conn: sqlite3.Connection, *, days: int) -> dict[str, Any]:
    since = f"-{days} days"
    runs = conn.execute(
        """
        SELECT run_id, source, project, model, started_at, peak_context_pct,
               total_input_tokens, total_output_tokens, total_cost, has_cost,
               cache_read_tokens, cache_creation_tokens, context_window
        FROM runs
        WHERE date(started_at) >= date('now', ?)
        ORDER BY started_at ASC
        """,
        (since,),
    ).fetchall()

    total_tokens = 0
    total_cost = 0.0
    has_cost_sessions = 0
    high_context: list[dict[str, Any]] = []
    model_costs_30d: dict[str, float] = defaultdict(float)
    runaway_sessions: list[dict[str, Any]] = []
    run_rows = list(runs)

    for r in run_rows:
        inp = int(r["total_input_tokens"] or 0)
        out = int(r["total_output_tokens"] or 0)
        total_tokens += inp + out
        if r["has_cost"]:
            has_cost_sessions += 1
            total_cost += float(r["total_cost"] or 0)
        pct = r["peak_context_pct"]
        if pct is not None and float(pct) >= 70:
            high_context.append({"run_id": str(r["run_id"]), "peak_context_pct": float(pct)})

    # 30-day model cost spread (independent of the insight window).
    model_rows = conn.execute(
        """
        SELECT model, SUM(total_cost) AS cost
        FROM runs
        WHERE date(started_at) >= date('now', '-30 days') AND has_cost = 1
        GROUP BY model
        """,
    ).fetchall()
    for r in model_rows:
        if r["model"] and float(r["cost"] or 0) > 0:
            model_costs_30d[str(r["model"])] = float(r["cost"])

    waste_rows = conn.execute(
        """
        SELECT e.waste_category, COUNT(*) AS n, SUM(e.waste_tokens) AS tokens
        FROM events e
        JOIN runs r ON r.run_id = e.run_id
        WHERE e.waste_category IS NOT NULL
          AND date(r.started_at) >= date('now', ?)
        GROUP BY waste_category
        """,
        (since,),
    ).fetchall()
    waste_by_cat: dict[str, dict[str, int]] = {}
    for row in waste_rows:
        waste_by_cat[str(row["waste_category"])] = {
            "events": int(row["n"]),
            "tokens": int(row["tokens"] or 0),
        }

    churn_rows = conn.execute(
        """
        SELECT path_rel, COUNT(*) AS n
        FROM events e
        JOIN runs r ON r.run_id = e.run_id
        WHERE e.tool_norm_name = 'edit' AND e.path_rel IS NOT NULL
          AND date(r.started_at) >= date('now', ?)
        GROUP BY path_rel
        HAVING n > 5
        """,
        (since,),
    ).fetchall()
    file_churn = {str(r["path_rel"]): int(r["n"]) for r in churn_rows}

    cache_stats = _cache_stats(conn, days=7)
    rebilling = _rebilling_aggregate(conn, run_rows, days=days)
    unused_tools = _unused_tools_aggregate(conn, run_rows, days=days)
    runaway_sessions = _runaway_aggregate(conn, run_rows)
    drift = _behavioral_drift(conn)
    quality = _quality_regression(conn)
    subagent_heavy = _subagent_heavy(conn, run_rows)

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
        "file_churn": file_churn,
        "cache_stats_7d": cache_stats,
        "model_costs_30d": dict(model_costs_30d),
        "runaway_sessions": runaway_sessions,
        "rebilling_tokens_14d": rebilling["tokens"],
        "rebilling_cost_14d": rebilling["cost_usd"],
        "unused_tools": unused_tools,
        "behavioral_drift": drift,
        "quality_regression": quality,
        "subagent_heavy": subagent_heavy,
    }


# ---------------------------------------------------------------------------
# Cache health (§2.7D)
# ---------------------------------------------------------------------------


def _cache_stats(conn: sqlite3.Connection, *, days: int) -> dict[str, Any]:
    since = f"-{days} days"
    rows = conn.execute(
        """
        SELECT date(started_at) AS day, cache_read_tokens, cache_creation_tokens,
               total_input_tokens, run_id
        FROM runs
        WHERE date(started_at) >= date('now', ?)
        """,
        (since,),
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
    spike_count = _cache_creation_spikes(conn, days=days)
    return {
        "cache_read": total_read,
        "cache_creation": total_creation,
        "daily": daily,
        "spike_count": spike_count,
    }


def _cache_creation_spikes(conn: sqlite3.Connection, *, days: int) -> int:
    """A turn where cache_creation > 50% of that turn's input tokens (cache thrash)."""
    rows = conn.execute(
        """
        SELECT e.cache_creation_tokens, e.input_tokens
        FROM events e
        JOIN runs r ON r.run_id = e.run_id
        WHERE e.cache_creation_tokens IS NOT NULL AND e.cache_creation_tokens > 0
          AND e.input_tokens IS NOT NULL AND e.input_tokens > 0
          AND date(r.started_at) >= date('now', ?)
        """,
        (f"-{days} days",),
    ).fetchall()
    spikes = 0
    for r in rows:
        cw = int(r["cache_creation_tokens"] or 0)
        inp = int(r["input_tokens"] or 0)
        if inp > 0 and cw / inp > 0.5:
            spikes += 1
    return spikes


# ---------------------------------------------------------------------------
# Re-billing aggregate (from cairn/profile)
# ---------------------------------------------------------------------------


def _rebilling_aggregate(
    conn: sqlite3.Connection, run_rows: list[sqlite3.Row], *, days: int
) -> dict[str, Any]:
    try:
        from cairn.profile.compute import decompose_run
        from cairn.profile.detectors import rebilling_waste_tokens
    except Exception:
        return {"tokens": 0, "cost_usd": 0.0}
    total_tokens = 0
    total_cost = 0.0
    for r in run_rows:
        events = _load_events(conn, str(r["run_id"]))
        if not events:
            continue
        model = str(r["model"]) if r["model"] else None
        try:
            result = decompose_run(events, model=model)
        except Exception:
            continue
        rebilled = rebilling_waste_tokens(events, result.regions)
        total_tokens += rebilled
        total_cost += float(result.rebilling_cost_usd or 0.0)
    return {"tokens": total_tokens, "cost_usd": round(total_cost, 6)}


# ---------------------------------------------------------------------------
# Unused-tool aggregate (from cairn/profile/detectors UNUSED_TOOL_SCHEMA)
# ---------------------------------------------------------------------------


def _unused_tools_aggregate(
    conn: sqlite3.Connection, run_rows: list[sqlite3.Row], *, days: int
) -> list[dict[str, Any]]:
    try:
        from cairn.profile.compute import _input_price_per_token, decompose_run
        from cairn.profile.detectors import detect_findings
    except Exception:
        return []
    by_tool: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"sessions": 0, "total_turns": 0, "wasted_tokens": 0, "use_fractions": []}
    )
    for r in run_rows:
        events = _load_events(conn, str(r["run_id"]))
        if not events:
            continue
        model = str(r["model"]) if r["model"] else None
        try:
            result = decompose_run(events, model=model)
            price = _input_price_per_token(model)
            findings = detect_findings(events, result.regions, input_price_per_token=price)
        except Exception:
            continue
        for f in findings:
            if f.type != "UNUSED_TOOL_SCHEMA":
                continue
            tool = str(f.detail.get("tool") or "unknown")
            entry = by_tool[tool]
            entry["sessions"] += 1
            entry["total_turns"] += int(f.detail.get("total_turns", 0))
            entry["wasted_tokens"] += int(f.tokens or 0)
            entry["use_fractions"].append(float(f.detail.get("use_fraction", 0.0)))
    out: list[dict[str, Any]] = []
    for tool, v in by_tool.items():
        if not v["use_fractions"]:
            continue
        # "Never called across 14d sessions" — a tool flagged unused whose
        # mean use fraction is <=0.1 (rarely/never used relative to turn count).
        mean_use = sum(v["use_fractions"]) / len(v["use_fractions"])
        if mean_use > 0.1:
            continue
        out.append(
            {
                "tool": tool,
                "sessions": v["sessions"],
                "total_turns": v["total_turns"],
                "wasted_tokens": v["wasted_tokens"],
                "tokens_per_turn": 60,
                "mean_use_fraction": round(mean_use, 4),
            }
        )
    out.sort(key=lambda t: t["wasted_tokens"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Runaway sessions — later-half per-turn input >3x first half
# ---------------------------------------------------------------------------


def _runaway_aggregate(
    conn: sqlite3.Connection, run_rows: list[sqlite3.Row]
) -> list[dict[str, Any]]:
    from cairn.metrics.normalized import is_runaway_vs_expectation

    out: list[dict[str, Any]] = []
    for r in run_rows:
        rows = conn.execute(
            """
            SELECT seq, type, input_tokens
            FROM events
            WHERE run_id = ? AND type = 'assistant_message'
              AND input_tokens IS NOT NULL AND input_tokens > 0
            ORDER BY seq
            """,
            (str(r["run_id"]),),
        ).fetchall()
        if len(rows) < 4:
            continue
        per_turn = [int(row["input_tokens"]) for row in rows]
        mid = len(per_turn) // 2
        first_avg = _safe_mean(per_turn[:mid])
        second_avg = _safe_mean(per_turn[mid:])
        if first_avg <= 0:
            continue
        ratio = second_avg / first_avg
        run_dict = dict(r)
        if is_runaway_vs_expectation(conn, run_dict, ratio=ratio):
            out.append({"run_id": str(r["run_id"]), "ratio": round(ratio, 2)})
    return out


def _safe_mean(xs: list[int]) -> float:
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


# ---------------------------------------------------------------------------
# Behavioral drift (from cairn/metrics/fingerprint)
# ---------------------------------------------------------------------------


def _behavioral_drift(conn: sqlite3.Connection) -> dict[str, Any]:
    try:
        from cairn.metrics.fingerprint import (
            _baseline_vectors_for,
            detect_drift,
            detect_gradual_drift,
        )
    except Exception:
        return {"drift": False}
    # Pick the project/model with the most recent-week fingerprints.
    key_row = conn.execute(
        """
        SELECT project, model, COUNT(*) AS n
        FROM fingerprints
        WHERE week = (SELECT MAX(week) FROM fingerprints)
        GROUP BY project, model
        ORDER BY n DESC LIMIT 1
        """
    ).fetchone()
    if key_row is None:
        return {"drift": False}
    project, model = str(key_row["project"] or ""), str(key_row["model"] or "")
    current_rows = conn.execute(
        "SELECT vector_json, week FROM fingerprints WHERE project = ? AND model = ? "
        "ORDER BY week DESC",
        (project, model),
    ).fetchall()
    if not current_rows:
        return {"drift": False}
    try:
        current_vec = json.loads(current_rows[0]["vector_json"])
        current_week = current_rows[0]["week"]
    except (json.JSONDecodeError, TypeError):
        return {"drift": False}

    baseline = _baseline_vectors_for(conn, project, model, before_week=current_week)
    drift_kind = "none"
    d_squared: float | None = None
    threshold: float | None = None
    top_dims: list[dict[str, Any]] = []
    joint_drift = False
    if len(baseline) >= 4:
        res = detect_drift(current_vec, baseline)
        if res.drift:
            joint_drift = True
            drift_kind = "joint_shock"
            d_squared = res.d_squared
            threshold = res.threshold
            # Top dimension deltas by absolute z-score.
            ranked = sorted(enumerate(res.per_dim_deltas), key=lambda kv: abs(kv[1]), reverse=True)
            labels = _fingerprint_labels()
            top_dims = [
                {"axis": labels[i] if i < len(labels) else f"dim{i}", "delta": float(z)}
                for i, z in ranked[:5]
                if z != 0.0
            ]

    # Gradual drift across weekly means.
    by_week: dict[str, list[list[float]]] = defaultdict(list)
    for r in current_rows:
        try:
            by_week[str(r["week"])].append(json.loads(r["vector_json"]))
        except (json.JSONDecodeError, TypeError):
            continue
    weekly_means: list[tuple[str, list[float]]] = []
    for w, vecs in sorted(by_week.items()):
        if vecs:
            mean = [sum(col) / len(col) for col in zip(*vecs, strict=False)]
            weekly_means.append((w, mean))
    gradual = detect_gradual_drift(weekly_means)
    gradual_drift = bool(gradual.get("drift"))

    if not joint_drift and gradual_drift:
        drift_kind = "gradual"
        for ax in gradual.get("axes", []):
            top_dims.append({"axis": _fingerprint_labels()[ax["axis"]], "delta": float(ax["ewma"])})

    if not (joint_drift or gradual_drift):
        return {"drift": False}
    return {
        "drift": True,
        "kind": drift_kind,
        "project": project,
        "model": model,
        "d_squared": d_squared,
        "threshold": threshold,
        "top_dims": top_dims[:5],
    }


def _fingerprint_labels() -> list[str]:
    return [
        "read",
        "edit",
        "bash",
        "search",
        "delete",
        "sub_agent",
        "read_write",
        "explore_exec",
        "retry",
        "error",
        "identical",
        "ctx_mean",
        "ctx_max",
        "ctx_slope",
        "ctx_final",
        "turns",
        "entropy",
        "reasoning",
        "avg_tokens",
        "out_in",
        "duration",
        "sub_count",
    ]


# ---------------------------------------------------------------------------
# Quality regression (from cairn/outcomes)
# ---------------------------------------------------------------------------


def _quality_regression(conn: sqlite3.Connection) -> dict[str, Any]:
    recent_rows = conn.execute(
        """
        SELECT o.quality_score
        FROM outcomes o JOIN runs r ON o.run_id = r.run_id
        WHERE r.started_at >= date('now', '-7 days')
          AND o.quality_score IS NOT NULL
        """
    ).fetchall()
    prior_rows = conn.execute(
        """
        SELECT o.quality_score
        FROM outcomes o JOIN runs r ON o.run_id = r.run_id
        WHERE r.started_at >= date('now', '-14 days')
          AND r.started_at < date('now', '-7 days')
          AND o.quality_score IS NOT NULL
        """
    ).fetchall()
    recent = [float(r["quality_score"]) for r in recent_rows]
    prior = [float(r["quality_score"]) for r in prior_rows]
    if not recent or not prior:
        return {
            "regressed": False,
            "recent_mean": None,
            "prior_mean": None,
            "drop_pct": None,
            "recent_n": len(recent),
            "prior_n": len(prior),
        }
    recent_mean = sum(recent) / len(recent)
    prior_mean = sum(prior) / len(prior)
    if prior_mean <= 0:
        return {
            "regressed": False,
            "recent_mean": round(recent_mean, 2),
            "prior_mean": round(prior_mean, 2),
            "drop_pct": None,
            "recent_n": len(recent),
            "prior_n": len(prior),
        }
    drop_pct = (prior_mean - recent_mean) / prior_mean * 100.0
    return {
        "regressed": drop_pct > 15.0,
        "recent_mean": round(recent_mean, 2),
        "prior_mean": round(prior_mean, 2),
        "drop_pct": round(drop_pct, 2),
        "recent_n": len(recent),
        "prior_n": len(prior),
    }


def _subagent_heavy(conn: sqlite3.Connection, run_rows: list[sqlite3.Row]) -> dict[str, Any] | None:
    from cairn.insights.rules import SUBAGENT_HEAVY_THRESHOLD

    success_labels = frozenset({"landed"})
    for r in run_rows:
        run_id = str(r["run_id"])
        outcome = conn.execute(
            "SELECT outcome_label FROM diagnostics WHERE run_id = ?", (run_id,)
        ).fetchone()
        label = str(outcome["outcome_label"]) if outcome and outcome["outcome_label"] else None
        if label in success_labels:
            continue
        rows = conn.execute(
            """
            SELECT agent_lane, input_tokens, output_tokens
            FROM events WHERE run_id = ? AND agent_lane IS NOT NULL
            """,
            (run_id,),
        ).fetchall()
        if not rows:
            continue
        total = 0
        subagent = 0
        for row in rows:
            tok = int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0)
            total += tok
            if str(row["agent_lane"]) in ("subagent", "sidechain"):
                subagent += tok
        if total <= 0:
            continue
        share = subagent / total
        if share > SUBAGENT_HEAVY_THRESHOLD:
            return {
                "run_id": run_id,
                "share_pct": round(share * 100, 1),
                "subagent_tokens": subagent,
            }
    return None


# ---------------------------------------------------------------------------


def _load_events(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM events WHERE run_id = ? ORDER BY seq", (run_id,)).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Rendering / weekly report (folded from render.py)
# ---------------------------------------------------------------------------


def render_feed(insights: list[Insight]) -> None:
    """Print the insight feed to stdout."""
    if not insights:
        print("No issues detected in the last 14 days. Your agents are running efficiently.")
        return
    for i in insights:
        icon = {"warning": "[!]", "suggestion": "[→]", "info": "[i]"}.get(i.severity, "[ ]")
        savings = f" ~${_fmt(i.savings_estimate)}/wk" if i.savings_estimate else ""
        print(f"{icon} {i.title}{savings}")
        print(f"    {i.body}")
        if i.action:
            print(f"    Action: {i.action}")
        print()


def weekly_markdown(ledger: Ledger, days: int = 7, now: datetime | None = None) -> str:
    """Return a weekly markdown report. ``now`` is injectable for deterministic tests."""
    if now is None:
        now = datetime.now(UTC)
    start = now - timedelta(days=days)
    totals = _window_totals(ledger, start.date().isoformat())
    insights = evaluate(ledger, days=days)
    lines = [
        "# Cairn weekly report",
        f"\nWeek of {start.date()} to {now.date()}\n",
        "## Totals",
        f"- Sessions: {totals['sessions']}",
        f"- Spend: ~${totals['cost']:,.2f}",
        f"- Tokens: {totals['tokens']:,} ({totals['input']:,} in / {totals['output']:,} out)",
        "",
    ]
    if totals["models"]:
        lines.append("## Model mix")
        for model, tok in sorted(totals["models"].items(), key=lambda kv: kv[1], reverse=True)[:5]:
            lines.append(f"- `{model}`: {tok:,} tok")
        lines.append("")
    if insights:
        lines.append("## Top insights")
        for i in insights[:5]:
            lines.append(f"- **{i.title}** — {i.body}")
        lines.append("")
    else:
        lines.append("No significant insights this week.\n")
    return "\n".join(lines)


def _window_totals(ledger: Ledger, start_day: str) -> dict[str, Any]:
    rows = ledger.connection.execute(
        """
        SELECT model, SUM(sessions) AS sessions, SUM(cost_total) AS cost,
               SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens
        FROM rollup_daily
        WHERE day >= ?
        GROUP BY model
        """,
        (start_day,),
    ).fetchall()
    sessions = sum(int(r["sessions"] or 0) for r in rows)
    cost = sum(float(r["cost"] or 0.0) for r in rows)
    inp = sum(int(r["input_tokens"] or 0) for r in rows)
    out = sum(int(r["output_tokens"] or 0) for r in rows)
    models = {
        str(r["model"]): int(r["input_tokens"] or 0) + int(r["output_tokens"] or 0) for r in rows
    }
    return {
        "sessions": sessions,
        "cost": cost,
        "input": inp,
        "output": out,
        "tokens": inp + out,
        "models": models,
    }


def _fmt(value: float | None) -> str:
    if value is None:
        return "0.00"
    return f"{value:,.2f}"
