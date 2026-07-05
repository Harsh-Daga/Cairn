"""Plan-window gauge: rolling token consumption per source."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from server.util.user_config import load_user_config

WINDOW_HOURS = 5


@dataclass
class WindowGauge:
    """Result of a plan-window gauge computation."""

    total_tokens: int
    by_source: dict[str, int]
    limit: int | None
    exceeded: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_hours": WINDOW_HOURS,
            "total_tokens": self.total_tokens,
            "by_source": self.by_source,
            "limit": self.limit,
            "exceeded": self.exceeded,
        }


def compute_gauge(root: Path) -> WindowGauge:
    """Compute rolling token gauge for the workspace at root."""
    db_path = root / ".cairn" / "cairn.db"
    if not db_path.is_file():
        return WindowGauge(total_tokens=0, by_source={}, limit=None, exceeded=False)

    cfg = load_user_config()
    limit = cfg.five_hour_tokens

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT source,
                   SUM(input_tokens + output_tokens
                       + COALESCE(cache_read_tokens, 0)
                       + COALESCE(cache_creation_tokens, 0)) AS tokens
            FROM traces
            WHERE started_at >= datetime('now', ?)
            GROUP BY source
            """,
            (f"-{WINDOW_HOURS} hours",),
        ).fetchall()
    finally:
        conn.close()

    by_source: dict[str, int] = {}
    total = 0
    for row in rows:
        src = str(row["source"] or "unknown")
        tokens = int(row["tokens"] or 0)
        by_source[src] = tokens
        total += tokens

    exceeded = limit is not None and total > limit
    return WindowGauge(total_tokens=total, by_source=by_source, limit=limit, exceeded=exceeded)
