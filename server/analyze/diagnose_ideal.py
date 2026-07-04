"""Ideal-path counterfactual savings."""

from __future__ import annotations

from typing import Any


def ideal_path_savings(events: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    """Minimal read-set estimate to reach edited files."""
    edited = {
        str(event.get("path_rel"))
        for event in events
        if event.get("tool_norm_name") == "edit" and event.get("path_rel")
    }
    if not edited:
        return 0, {"reads_actual": 0, "reads_ideal": 0, "edited": []}

    read_paths: list[str] = []
    read_tokens = 0
    for event in events:
        if event.get("tool_norm_name") in {"read", "search"} and event.get("path_rel"):
            read_paths.append(str(event["path_rel"]))
            read_tokens += int(event.get("input_tokens") or 0) + int(
                event.get("output_tokens") or 0
            )

    ideal_reads = 0
    for target in edited:
        parts = target.split("/")
        ideal_reads += max(1, len(parts) - 1)
    ideal_reads = min(ideal_reads, len(edited) * 2)
    actual_reads = len(read_paths)
    if actual_reads <= ideal_reads:
        return 0, {
            "reads_actual": actual_reads,
            "reads_ideal": ideal_reads,
            "edited": sorted(edited),
            "note": "actual reads already at or below ideal estimate",
        }

    redundant_reads = actual_reads - ideal_reads
    average_tokens = read_tokens / actual_reads if actual_reads else 0
    savings = int(redundant_reads * average_tokens) if average_tokens > 0 else 0
    return max(savings, 0), {
        "reads_actual": actual_reads,
        "reads_ideal": ideal_reads,
        "edited": sorted(edited),
        "redundant_reads": redundant_reads,
    }


__all__ = ["ideal_path_savings"]
