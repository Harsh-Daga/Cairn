"""Read-only MCP context-budget composition for one session."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

_REGION_ORDER = (
    "system",
    "tool_schema",
    "tool_result",
    "retrieved",
    "user",
    "history",
)

_REMOVABLE_REGIONS = frozenset({"system", "tool_schema", "tool_result", "retrieved", "history"})

_TRIM_ADVICE = {
    "system": "Shorten stable system instructions or move optional guidance behind retrieval.",
    "tool_schema": "Load only tool schemas needed for the current step.",
    "tool_result": (
        "Summarize large tool results after extracting needed facts; avoid re-billing stale output."
    ),
    "retrieved": "Deduplicate retrieval and reduce overlapping chunks.",
    "history": "Compact resolved history while retaining decisions and verification evidence.",
}


def context_budget(
    conn: sqlite3.Connection,
    workspace_id: str | None,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Return current/selected session context composition and one trim suggestion."""
    requested = str(args.get("trace_id") or args.get("session_id") or "").strip() or None
    resolution = resolve_trace(conn, workspace_id, requested)
    if resolution.get("error"):
        return resolution

    trace_id = str(resolution["trace_id"])
    trace = resolution["trace"]
    assert isinstance(trace, sqlite3.Row)

    regions = conn.execute(
        """
        SELECT cr.region, cr.tokens, cr.cost, cr.content_hash, cr.first_turn,
               cr.last_seen_turn, cr.still_in_window, cr.span_id, s.seq
        FROM context_regions cr
        JOIN spans s ON s.span_id = cr.span_id
        WHERE s.trace_id = ?
        ORDER BY cr.tokens DESC, s.seq ASC
        """,
        (trace_id,),
    ).fetchall()

    composition = _composition(regions)
    total_region_tokens = sum(int(item["tokens"]) for item in composition)
    removable = _removable_regions(regions)
    suggestion = _trim_suggestion(removable)
    data_as_of = _data_as_of(trace, regions)
    estimate_status = _estimate_status(trace, total_region_tokens)

    peak = trace["peak_context_pct"]
    window = trace["context_window"]
    return {
        "trace_id": trace_id,
        "title": trace["title"],
        "status": trace["status"],
        "data_as_of": data_as_of,
        "estimate_status": estimate_status,
        "read_only": True,
        "provider_call": False,
        "context_window": int(window) if window is not None else None,
        "peak_context_pct": float(peak) if peak is not None else None,
        "trace_input_tokens": int(trace["input_tokens"] or 0),
        "trace_output_tokens": int(trace["output_tokens"] or 0),
        "composition": composition,
        "total_region_tokens": total_region_tokens,
        "largest_removable": removable[:5],
        "suggestion": suggestion,
        "limitations": _limitations(regions, total_region_tokens, estimate_status),
        "consultation": "recorded",
    }


def resolve_trace(
    conn: sqlite3.Connection,
    workspace_id: str | None,
    requested: str | None,
) -> dict[str, Any]:
    ws = "AND workspace_id = ?" if workspace_id else ""
    params: list[Any] = [workspace_id] if workspace_id else []

    if requested:
        row = conn.execute(
            f"SELECT * FROM traces WHERE trace_id = ? {ws}",
            [requested, *params],
        ).fetchone()
        if row is None:
            return {
                "error": "trace_not_found",
                "trace_id": requested,
                "message": "No session matches the supplied trace_id in this workspace ledger.",
                "read_only": True,
                "provider_call": False,
            }
        return {"trace_id": requested, "trace": row}

    active = conn.execute(
        f"""
        SELECT trace_id, started_at, status
        FROM traces
        WHERE 1=1 {ws}
          AND (status = 'running' OR ended_at IS NULL)
        ORDER BY started_at DESC
        LIMIT 3
        """,
        params,
    ).fetchall()
    if len(active) > 1:
        return {
            "error": "ambiguous_session",
            "message": (
                "Multiple active sessions found; pass an explicit trace_id "
                "(or session_id) to cairn_context_budget."
            ),
            "candidates": [
                {
                    "trace_id": str(row["trace_id"]),
                    "started_at": row["started_at"],
                    "status": row["status"],
                }
                for row in active
            ],
            "read_only": True,
            "provider_call": False,
        }

    row = conn.execute(
        f"SELECT * FROM traces WHERE 1=1 {ws} ORDER BY started_at DESC LIMIT 1",
        params,
    ).fetchone()
    if row is None:
        return {
            "error": "no_sessions",
            "message": "No sessions in ledger; nothing to budget.",
            "trace_id": None,
            "read_only": True,
            "provider_call": False,
            "composition": [],
            "largest_removable": [],
            "suggestion": None,
            "estimate_status": "unavailable",
            "data_as_of": None,
        }
    return {"trace_id": str(row["trace_id"]), "trace": row}


def _composition(regions: list[sqlite3.Row]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {
        name: {
            "region": name,
            "tokens": 0,
            "cost": 0.0,
            "spans": 0,
            "still_in_window_spans": 0,
        }
        for name in _REGION_ORDER
    }
    for row in regions:
        name = str(row["region"])
        bucket = buckets.setdefault(
            name,
            {
                "region": name,
                "tokens": 0,
                "cost": 0.0,
                "spans": 0,
                "still_in_window_spans": 0,
            },
        )
        bucket["tokens"] = int(bucket["tokens"]) + int(row["tokens"] or 0)
        bucket["cost"] = float(bucket["cost"]) + float(row["cost"] or 0.0)
        bucket["spans"] = int(bucket["spans"]) + 1
        if int(row["still_in_window"] or 0):
            bucket["still_in_window_spans"] = int(bucket["still_in_window_spans"]) + 1
    ordered = [buckets[name] for name in _REGION_ORDER if int(buckets[name]["tokens"]) > 0]
    extras = [
        bucket
        for name, bucket in buckets.items()
        if name not in _REGION_ORDER and int(bucket["tokens"]) > 0
    ]
    return ordered + extras


def _removable_regions(regions: list[sqlite3.Row]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in regions:
        region = str(row["region"])
        if region not in _REMOVABLE_REGIONS:
            continue
        tokens = int(row["tokens"] or 0)
        if tokens <= 0:
            continue
        still = bool(int(row["still_in_window"] or 0))
        stale = not still
        candidates.append(
            {
                "region": region,
                "tokens": tokens,
                "cost": float(row["cost"] or 0.0),
                "span_id": str(row["span_id"]),
                "seq": int(row["seq"] or 0),
                "content_hash": row["content_hash"],
                "first_turn": row["first_turn"],
                "last_seen_turn": row["last_seen_turn"],
                "still_in_window": still,
                "stale": stale,
                "removable_reason": (
                    "no longer in window" if stale else "large region still in window"
                ),
            }
        )
    candidates.sort(key=lambda item: (0 if item["stale"] else 1, -int(item["tokens"])))
    return candidates


def _trim_suggestion(removable: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not removable:
        return None
    target = removable[0]
    region = str(target["region"])
    return {
        "action": "trim_region",
        "region": region,
        "span_id": target["span_id"],
        "tokens": target["tokens"],
        "conservative": True,
        "advice": _TRIM_ADVICE.get(
            region,
            "Inspect the largest removable region before changing retention.",
        ),
        "limitation": (
            "Suggestion is descriptive from recorded region sizes; Cairn does not mutate "
            "provider context or claim avoidable savings."
        ),
    }


def _data_as_of(trace: sqlite3.Row, regions: list[sqlite3.Row]) -> str | None:
    del regions  # Region rows lack timestamps; trace bounds are the freshness signal.
    for value in (trace["ended_at"], trace["started_at"]):
        if value:
            return str(value)
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _estimate_status(trace: sqlite3.Row, total_region_tokens: int) -> str:
    if total_region_tokens > 0:
        return "measured"
    if int(trace["input_tokens"] or 0) > 0 or int(trace["output_tokens"] or 0) > 0:
        return "estimated"
    return "unavailable"


def _limitations(
    regions: list[sqlite3.Row],
    total_region_tokens: int,
    estimate_status: str,
) -> list[str]:
    notes = [
        "Read-only local ledger view; no provider or network call is made.",
        "User-region tokens are never offered as removable.",
    ]
    if not regions:
        notes.append(
            "No context_regions rows for this session; composition is empty and any "
            "token totals fall back to trace rollups when present."
        )
    elif estimate_status == "estimated":
        notes.append("Region rows are incomplete relative to trace token rollups.")
    if total_region_tokens == 0 and estimate_status == "unavailable":
        notes.append("No token evidence recorded for this session yet.")
    return notes
