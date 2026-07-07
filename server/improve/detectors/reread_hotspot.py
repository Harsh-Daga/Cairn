"""Repeated reads of unchanged file content."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight


def rule_reread_hotspot(ctx: dict[str, Any]) -> Insight | None:
    rereads = ctx.get("read_rereads") or []
    if not isinstance(rereads, list) or not rereads:
        return None
    worst = max(rereads, key=lambda item: int(item.get("reads", 0)))
    path = str(worst.get("path", "file"))
    reads = int(worst.get("reads", 0))
    if reads < 3:
        return None
    return Insight(
        id="reread-hotspot",
        severity="info",
        title=f"Repeated reads: {path}",
        body=(
            f"{path} was read {reads} times with unchanged content. "
            "Cache file contents in agent memory or narrow read scope."
        ),
        evidence={"path": path, "reads": reads, "content_hash": worst.get("content_hash")},
        savings_estimate=None,
        action="cairn optimize",
    )
