"""Compute per-run data quality provenance (Phase 0)."""

from __future__ import annotations

import json
from typing import Any

from cairn.ingest.usage import ObservedUsage

PARSER_VERSION = "2.0.0"


def compute_data_quality(
    *,
    flat_rows: list[dict[str, Any]],
    observed: ObservedUsage,
    has_cost: bool,
    has_timestamps: bool,
    cost_was_priced: bool,
    dropped_events: int = 0,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    """Return a row dict for the ``data_quality`` table."""
    measured = 0
    estimated = 0
    for row in flat_rows:
        inp = row.get("input_tokens")
        if isinstance(inp, int) and inp > 0:
            if row.get("input_estimated"):
                estimated += inp
            else:
                measured += inp
        out = row.get("output_tokens")
        if isinstance(out, int) and out > 0:
            if row.get("output_estimated"):
                estimated += out
            else:
                measured += out

    total = measured + estimated
    if total > 0:
        pct_measured = round(100.0 * measured / total, 2)
        pct_estimated = round(100.0 * estimated / total, 2)
    else:
        pct_measured = None
        pct_estimated = None

    if has_cost:
        if observed.cost is not None:
            cost_source = "observed"
        elif cost_was_priced:
            cost_source = "priced"
        else:
            cost_source = "absent"
    else:
        cost_source = "absent"

    quality_notes = list(notes or [])
    if observed.input_estimated and observed.input_estimation_error_pct is not None:
        quality_notes.append(
            f"input estimated via {observed.input_estimation_method} "
            f"(±{observed.input_estimation_error_pct:.0f}%)"
        )
    if observed.output_estimated and observed.output_estimation_error_pct is not None:
        quality_notes.append(
            f"output estimated via {observed.output_estimation_method} "
            f"(±{observed.output_estimation_error_pct:.0f}%)"
        )

    return {
        "pct_tokens_measured": pct_measured,
        "pct_tokens_estimated": pct_estimated,
        "timestamps_present": 1 if has_timestamps else 0,
        "cost_source": cost_source,
        "parser_version": PARSER_VERSION,
        "dropped_events": dropped_events,
        "notes_json": json.dumps(quality_notes) if quality_notes else None,
    }
