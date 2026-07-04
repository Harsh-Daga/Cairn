"""Failure localization via changepoint scan — Phase A."""

from __future__ import annotations

from typing import Any


def localize_failure(events: list[dict[str, Any]]) -> tuple[int | None, str | None, str]:
    """Return (failure_origin_event_id, signature, one_liner)."""
    if not events:
        return None, None, "empty session"

    features: list[tuple[int, float]] = []
    error_rate_window: list[int] = []
    for e in events:
        eid = e.get("event_id")
        if eid is None:
            continue
        err = 1 if e.get("tool_is_error") else 0
        waste = int(e.get("waste_tokens") or 0)
        tok = int(e.get("input_tokens") or 0) + int(e.get("output_tokens") or 0)
        error_rate_window.append(err)
        window = error_rate_window[-5:]
        err_rate = sum(window) / len(window)
        score = err_rate * 10.0 + (waste / max(tok, 1)) * 5.0
        features.append((int(eid), score))

    if len(features) < 3:
        return None, None, "insufficient events for localization"

    # Changepoint: first index where trailing mean exceeds leading mean by multiplier persistently.
    from cairn.config import get_diagnose_setting

    multiplier = float(get_diagnose_setting("changepoint_multiplier"))
    scores = [s for _, s in features]
    mid = len(scores) // 2
    lead = sum(scores[:mid]) / max(mid, 1)
    for i in range(mid, len(scores) - 1):
        trail = sum(scores[i:]) / max(len(scores) - i, 1)
        if lead > 0 and trail > lead * multiplier and trail > 0.5:
            eid, sig_score = features[i]
            sig = f"error_waste_spike:{sig_score:.2f}"
            return eid, sig, f"Trajectory degraded after event {eid} (error/waste spike)"

    worst = max(features, key=lambda x: x[1])
    if worst[1] > 1.0:
        return (
            worst[0],
            f"peak_badness:{worst[1]:.2f}",
            f"Highest failure signal at event {worst[0]}",
        )
    return None, None, "no clear failure origin detected"
