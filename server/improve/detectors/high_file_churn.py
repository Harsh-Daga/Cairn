"""High file edit churn detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight


def rule_high_file_churn(ctx: dict[str, Any]) -> Insight | None:
    churn = ctx.get("file_churn", {})
    if not churn:
        return None
    path, count = max(churn.items(), key=lambda kv: kv[1])
    if count <= 5:
        return None
    return Insight(
        id="high-file-churn",
        severity="info",
        title=f"High edit churn: {path}",
        body=(
            f"{path}: {count} edits across sessions. "
            "Consider writing tests before making multiple edit attempts."
        ),
        evidence={"path": path, "edits": count},
        savings_estimate=None,
        action="cairn optimize",
    )
