"""Normalize and classify tool identities for analytics surfaces."""

from __future__ import annotations

from typing import Literal

from server.ingest.constants import (
    CANONICAL_NORMS,
    NORM_BASH,
    normalize_tool_name,
)

ToolFamily = Literal["builtin", "mcp", "shell", "unknown"]


def classify_tool(raw_name: str | None, *, source: str) -> tuple[str, str, ToolFamily]:
    """Return ``(display_name, normalized_id, family)`` for one tool span."""
    raw = (raw_name or "").strip() or "unknown"
    normalized = normalize_tool_name(raw, source=source)
    family = tool_family(normalized, raw)
    display = raw if raw != "unknown" else normalized
    return display, normalized, family


def tool_family(normalized: str, raw: str) -> ToolFamily:
    lowered = raw.lower()
    if normalized.startswith("mcp:") or lowered.startswith("mcp:") or lowered.startswith("mcp__"):
        return "mcp"
    if normalized == NORM_BASH:
        return "shell"
    if normalized in CANONICAL_NORMS:
        return "builtin"
    return "unknown"


def percentile(values: list[int], pct: float) -> float | None:
    """Nearest-rank percentile for non-empty integer samples."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return float(ordered[rank])
