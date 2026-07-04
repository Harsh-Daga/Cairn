"""Failure localization via changepoint scan."""

from __future__ import annotations

from typing import Any

from cairn.config import get_diagnose_setting


def localize_failure(events: list[dict[str, Any]]) -> tuple[int | None, str | None, str]:
    """Return (failure_origin_seq, signature, one_liner)."""
    if not events:
        return None, None, "empty session"

    features: list[tuple[int, float]] = []
    error_rate_window: list[int] = []
    for event in events:
        seq = event.get("seq")
        if not isinstance(seq, int):
            continue
        error = 1 if event.get("tool_is_error") else 0
        waste = int(event.get("waste_tokens") or 0)
        tokens = int(event.get("input_tokens") or 0) + int(event.get("output_tokens") or 0)
        error_rate_window.append(error)
        window = error_rate_window[-5:]
        error_rate = sum(window) / len(window)
        score = error_rate * 10.0 + (waste / max(tokens, 1)) * 5.0
        features.append((seq, score))

    if len(features) < 3:
        return None, None, "insufficient events for localization"

    multiplier = float(get_diagnose_setting("changepoint_multiplier"))
    scores = [score for _, score in features]
    midpoint = len(scores) // 2
    lead = sum(scores[:midpoint]) / max(midpoint, 1)
    for index in range(midpoint, len(scores) - 1):
        trail = sum(scores[index:]) / max(len(scores) - index, 1)
        if lead > 0 and trail > lead * multiplier and trail > 0.5:
            seq, score = features[index]
            signature = f"error_waste_spike:{score:.2f}"
            return seq, signature, f"Trajectory degraded after seq {seq} (error/waste spike)"

    worst_seq, worst_score = max(features, key=lambda item: item[1])
    if worst_score > 1.0:
        return (
            worst_seq,
            f"peak_badness:{worst_score:.2f}",
            f"Highest failure signal at seq {worst_seq}",
        )
    return None, None, "no clear failure origin detected"


__all__ = ["localize_failure"]
