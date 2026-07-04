"""Pillar 1 integration — decompose, store, detect, and serve context regions."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from cairn.profile.decompose import DecomposeResult, decompose_session
from cairn.profile.detectors import detect_findings, rebilling_waste_tokens


def _input_price_per_token(model: str | None) -> float | None:
    if not model:
        return None
    from cairn.pricing.data import match_model

    row = match_model(str(model))
    if row is None or row.input_per_mtok <= 0:
        return None
    return row.input_per_mtok / 1_000_000.0


def decompose_run(
    events: list[dict[str, Any]],
    *,
    model: str | None,
) -> DecomposeResult:
    """Decompose a run's events into regions (no ledger writes)."""
    return decompose_session(
        events, model=model, input_price_per_token=_input_price_per_token(model)
    )


def rebilling_for_run(
    writer: Any,
    run_id: str,
    *,
    events: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> int:
    """Compute + store context regions for a run; return re-billed stale tokens.

    Idempotent: clears prior ``context_regions`` rows for the run first. The
    returned token count feeds ``metrics/waste.py``'s ``REBILLING_WASTE`` hook.
    """
    conn = writer.connection
    if events is None:
        events = writer.load_events(run_id)
    if model is None:
        row = conn.execute("SELECT model FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        model = str(row["model"]) if row and row["model"] else None

    result = decompose_run(events, model=model)
    # Clear prior rows for idempotency, then write.
    conn.execute(
        "DELETE FROM context_regions WHERE event_id IN "
        "(SELECT event_id FROM events WHERE run_id = ?)",
        (run_id,),
    )
    writer.write_context_regions(run_id, [r.as_dict() for r in result.regions])
    return rebilling_waste_tokens(events, result.regions)


def profile_run(writer: Any, run_id: str) -> dict[str, Any]:
    """Full profile for a run: regions + findings + rebilling $ (writes nothing
    beyond what ``rebilling_for_run`` already wrote)."""
    conn = writer.connection
    events = writer.load_events(run_id)
    run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        return {
            "run_id": run_id,
            "regions": [],
            "findings": [],
            "rebilling": None,
            "data_notes": ["run not found"],
        }
    model = str(run["model"]) if run["model"] else None
    price = _input_price_per_token(model)
    result = decompose_run(events, model=model)
    peak = float(run["peak_context_pct"]) if run["peak_context_pct"] is not None else None
    findings = detect_findings(
        events, result.regions, input_price_per_token=price, peak_context_pct=peak
    )
    rebilling = {
        "tokens": rebilling_waste_tokens(events, result.regions),
        "cost_usd": result.rebilling_cost_usd,
        "estimated": result.estimated,
    }
    return {
        "run_id": run_id,
        "model": model,
        "turn_count": result.turn_count,
        "regions": [r.as_dict() for r in result.regions],
        "findings": [f.as_dict() for f in findings],
        "rebilling": rebilling,
        "data_notes": result.data_notes,
    }


def profile_payload(conn: Any, *, run_id: str) -> dict[str, Any]:
    """API payload for ``GET /api/profile/{run_id}`` — reads stored regions."""
    run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        return {
            "run_id": run_id,
            "regions": None,
            "findings": None,
            "rebilling": None,
            "data_notes": ["run not found"],
        }
    rows = conn.execute(
        "SELECT * FROM context_regions cr JOIN events e ON cr.event_id = e.event_id "
        "WHERE e.run_id = ? ORDER BY cr.region, cr.first_turn",
        (run_id,),
    ).fetchall()
    regions = [
        {
            "event_id": r["event_id"],
            "region": r["region"],
            "tokens": int(r["tokens"]),
            "cost": float(r["cost"]),
            "content_hash": r["content_hash"],
            "first_turn": r["first_turn"],
            "last_seen_turn": r["last_seen_turn"],
            "still_in_window": bool(r["still_in_window"]),
            "estimated": 0,  # stored rows do not persist estimated flag; derived
        }
        for r in rows
    ]
    has_cost = bool(run["has_cost"])
    # Recompute findings from stored events for a fresh detector pass.
    events = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY seq", (run_id,)
        ).fetchall()
    ]
    model = str(run["model"]) if run["model"] else None
    price = _input_price_per_token(model)
    result = decompose_run(events, model=model)
    peak = float(run["peak_context_pct"]) if run["peak_context_pct"] is not None else None
    findings = detect_findings(
        events, result.regions, input_price_per_token=price, peak_context_pct=peak
    )
    rebilling = {
        "tokens": rebilling_waste_tokens(events, result.regions),
        "cost_usd": result.rebilling_cost_usd if price else None,
    }
    data_notes: list[str] = result.data_notes
    if not has_cost:
        data_notes.append("has_cost=0: detector token counts are structural; $ values are null/0")
    # Null-on-empty: when there are no regions, surface nulls not zeros.
    if not regions:
        return {
            "run_id": run_id,
            "regions": None,
            "findings": None,
            "rebilling": None,
            "data_notes": data_notes or ["no context regions for this run"],
        }
    return {
        "run_id": run_id,
        "regions": regions,
        "findings": [f.as_dict() for f in findings],
        "rebilling": rebilling,
        "data_notes": data_notes,
    }


def recoverable_payload(conn: Any, *, days: int = 30) -> dict[str, Any]:
    """Aggregate recoverable $/wk across sessions (``GET /api/recoverable``)."""
    rows = conn.execute(
        """
        SELECT r.run_id, r.started_at, r.has_cost, r.model
        FROM runs r
        WHERE r.started_at >= date('now', ?)
        ORDER BY r.started_at DESC
        """,
        (f"-{days} days",),
    ).fetchall()
    by_week: dict[str, dict[str, float]] = defaultdict(lambda: {"tokens": 0.0, "cost_usd": 0.0})
    total_tokens = 0
    total_cost = 0.0
    has_any = False
    has_cost_any = False
    for r in rows:
        events = [
            dict(e)
            for e in conn.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY seq", (r["run_id"],)
            ).fetchall()
        ]
        if not events:
            continue
        model = str(r["model"]) if r["model"] else None
        result = decompose_run(events, model=model)
        if result.rebilling_tokens > 0 or result.regions:
            has_any = True
        if r["has_cost"]:
            has_cost_any = True
        week = str(r["started_at"] or "")[:10]
        # Group by ISO week (Mon-based) from the date.
        iso_week = _iso_week(week)
        by_week[iso_week]["tokens"] += result.rebilling_tokens
        by_week[iso_week]["cost_usd"] += result.rebilling_cost_usd
        total_tokens += result.rebilling_tokens
        total_cost += result.rebilling_cost_usd

    weeks = [
        {"week": w, "tokens": int(v["tokens"]), "cost_usd": round(v["cost_usd"], 6)}
        for w, v in sorted(by_week.items())
    ]
    data_notes: list[str] = []
    if not has_cost_any:
        data_notes.append("has_cost=0 for all sessions: recoverable $ is null (no input price)")
    if not has_any:
        return {
            "weeks": None,
            "total_tokens": None,
            "total_cost_usd": None,
            "data_notes": data_notes or ["no recoverable waste in range"],
        }
    return {
        "weeks": weeks,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6) if has_cost_any else None,
        "data_notes": data_notes,
    }


def _iso_week(day: str) -> str:
    """Return ISO year-week for a YYYY-MM-DD string; pass-through if unparseable."""
    try:
        from datetime import date

        y, m, d = (int(x) for x in day.split("-"))
        return f"{date(y, m, d).isocalendar().year}-W{date(y, m, d).isocalendar().week:02d}"
    except (ValueError, OSError):
        return day or "unknown"
