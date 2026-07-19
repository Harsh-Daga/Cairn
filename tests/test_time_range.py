"""Cross-layer UTC half-open time-range contract."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from server.api.time_range import resolve_values

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def test_presets_and_legacy_days_are_rolling_utc_ranges() -> None:
    preset = resolve_values(preset="24h", timezone="Asia/Kolkata", now=NOW)
    assert preset.start == "2026-07-16T12:00:00+00:00"
    assert preset.end == "2026-07-17T12:00:00+00:00"
    assert preset.prior_start == "2026-07-15T12:00:00+00:00"
    assert preset.prior_end == preset.start
    assert preset.semantics == "rolling_duration"
    assert preset.timezone == "Asia/Kolkata"

    legacy = resolve_values(days=7, now=NOW)
    assert legacy.duration_days == 7
    assert legacy.legacy_days == 7


def test_naive_custom_calendar_range_uses_declared_timezone_and_half_open_bounds() -> None:
    resolved = resolve_values(
        start=datetime(2026, 7, 1),
        end=datetime(2026, 7, 2),
        timezone="Asia/Kolkata",
        now=NOW,
    )
    assert resolved.start == "2026-06-30T18:30:00+00:00"
    assert resolved.end == "2026-07-01T18:30:00+00:00"
    assert resolved.semantics == "custom_calendar"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"days": 7, "preset": "7d"}, "either legacy days"),
        ({"start": datetime(2026, 7, 1)}, "both start and end"),
        (
            {"start": datetime(2026, 7, 2), "end": datetime(2026, 7, 1)},
            "start must be before end",
        ),
        ({"timezone": "Mars/Olympus"}, "Unknown IANA timezone"),
    ],
)
def test_ambiguous_or_invalid_ranges_are_actionable(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(HTTPException, match=message):
        resolve_values(**kwargs, now=NOW)  # type: ignore[arg-type]
