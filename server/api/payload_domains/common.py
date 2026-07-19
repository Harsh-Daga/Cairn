"""Shared time bounds and data-quality notes for payload builders."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from server.api.schemas import DataNote
from server.models.time_range import ResolvedTimeRange


def bounds(days: int, time_range: ResolvedTimeRange | None) -> tuple[str, str, int]:
    if time_range is not None:
        return time_range.start, time_range.end, time_range.duration_days
    now = datetime.now(UTC)
    return (now - timedelta(days=days)).isoformat(), now.isoformat(), days


def day_key(started_at: object | None, zone: ZoneInfo) -> str | None:
    """Parse a store timestamp into a calendar day, or None if unusable."""
    if not started_at:
        return None
    raw = str(started_at).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(zone).date().isoformat()


def append_truncation(limitations: list[str], note: str | None) -> None:
    """Append a truncation note when the analytics sample was capped."""
    if note:
        limitations.append(note)


def resolved_range(
    *, days: int, since: str, end: str, time_range: ResolvedTimeRange | None
) -> ResolvedTimeRange:
    return time_range or ResolvedTimeRange(
        start=since,
        end=end,
        prior_start=(
            datetime.fromisoformat(since)
            - (datetime.fromisoformat(end) - datetime.fromisoformat(since))
        ).isoformat(),
        prior_end=since,
        timezone="UTC",
        preset=None,
        legacy_days=days,
        semantics="rolling_duration",
        duration_days=days,
    )


def data_notes(
    conn: sqlite3.Connection, *, workspace_id: str, since: str, end: str
) -> list[DataNote]:
    rows = conn.execute(
        """
        SELECT source, COUNT(*) AS n
        FROM traces
        WHERE workspace_id = ? AND started_at >= ? AND started_at < ?
          AND cost_source = 'absent'
        GROUP BY source
        """,
        (workspace_id, since, end),
    ).fetchall()
    notes = [
        DataNote(
            source=str(row["source"]),
            sessions=int(row["n"]),
            issue="no_cost_data",
            message=f"{int(row['n'])} {row['source']} trace(s) have no reliable cost/token data.",
        )
        for row in rows
    ]
    from server.ingest.pricing import pricing_status

    status = pricing_status(None)
    if status.get("stale"):
        notes.append(
            DataNote(
                source="pricing",
                sessions=0,
                issue="stale_pricing",
                message=(
                    f"Bundled model prices (v{status['version']}, effective "
                    f"{status['effective_date']}) are stale "
                    f"({status['age_days']}d > {status['stale_after_days']}d). "
                    "Spend figures may be wrong; use local pricing overrides."
                ),
            )
        )
    return notes
