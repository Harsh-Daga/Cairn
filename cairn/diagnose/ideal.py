"""Ideal-path counterfactual — Phase A."""

from __future__ import annotations

from typing import Any


def ideal_path_savings(events: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    """Minimal read-set to reach edited files; return (token_savings, explain)."""
    edited = {
        str(e.get("path_rel"))
        for e in events
        if e.get("tool_norm_name") == "edit" and e.get("path_rel")
    }
    if not edited:
        return 0, {"reads_actual": 0, "reads_ideal": 0, "edited": []}

    read_paths: list[str] = []
    read_tokens = 0
    for e in events:
        if e.get("tool_norm_name") in ("read", "search") and e.get("path_rel"):
            read_paths.append(str(e["path_rel"]))
            read_tokens += int(e.get("input_tokens") or 0) + int(e.get("output_tokens") or 0)

    # BFS over directory prefixes: ideal = one read per edited file's directory chain.
    ideal_reads = 0
    for target in edited:
        parts = target.split("/")
        ideal_reads += max(1, len(parts) - 1)  # path components to navigate
    ideal_reads = min(ideal_reads, len(edited) * 2)
    actual_reads = len(read_paths)
    if actual_reads <= ideal_reads:
        return 0, {
            "reads_actual": actual_reads,
            "reads_ideal": ideal_reads,
            "edited": sorted(edited),
            "note": "actual reads already at or below ideal estimate",
        }

    # Token savings proportional to redundant reads (honest estimate, not fabricated exact).
    redundant = actual_reads - ideal_reads
    avg_tok = read_tokens / actual_reads if actual_reads else 0
    savings = int(redundant * avg_tok) if avg_tok > 0 else 0
    return max(savings, 0), {
        "reads_actual": actual_reads,
        "reads_ideal": ideal_reads,
        "edited": sorted(edited),
        "redundant_reads": redundant,
    }
