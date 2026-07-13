"""Incremental waste view — applies compute_waste to spans."""

from __future__ import annotations

import sqlite3

from server.analyze.events import spans_to_events
from server.analyze.views import IncrementalView, trace_input_hash
from server.analyze.waste import compute_waste
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo


def _peak_context_pct(events: list[dict[str, object]]) -> float | None:
    peak = 0
    window = 200_000
    for event in events:
        ctx = event.get("context_tokens_after")
        if isinstance(ctx, (int, float)) and ctx > 0:
            peak = max(peak, int(ctx))
    if peak <= 0:
        return None
    return round(peak / window * 100, 1)


class WasteView(IncrementalView):
    """Classify waste and update span + trace rollups."""

    view_name = "waste"
    VERSION = 1

    def keys_for(self, trace_id: str) -> list[str]:
        return [trace_id]

    def input_hash_for(self, conn: sqlite3.Connection, key: str) -> str:
        return trace_input_hash(conn, key)

    def compute(self, conn: sqlite3.Connection, key: str) -> None:
        trace = TraceRepo.get(conn, key)
        if trace is None:
            return
        spans = SpanRepo.list_by_trace(conn, key)
        events = spans_to_events(spans)
        has_cost = trace.cost_source in {"observed", "priced"}
        peak_pct = _peak_context_pct(events)
        waste = compute_waste(events, has_cost=has_cost, peak_context_pct=peak_pct)
        by_seq = {seq: (cat, tok) for seq, cat, tok in waste.tags}
        for span in spans:
            tag = by_seq.get(span.seq)
            if tag is None:
                continue
            category, tokens = tag
            updated = span.model_copy(update={"waste_category": category, "waste_tokens": tokens})
            SpanRepo.update(conn, updated)
        TraceRepo.update(
            conn,
            trace.model_copy(
                update={
                    "waste_tokens": waste.total_waste_tokens,
                    "peak_context_pct": peak_pct,
                }
            ),
        )
