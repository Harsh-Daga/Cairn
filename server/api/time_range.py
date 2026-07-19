"""FastAPI resolver for legacy and explicit time ranges."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, Query

from server.models.time_range import ResolvedTimeRange

Preset = Literal["24h", "7d", "30d", "90d"]
PRESET_DAYS: dict[Preset, int] = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}


def _invalid(message: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"error": {"code": "invalid_time_range", "message": message}},
    )


def resolve_values(
    *,
    days: int | None = None,
    preset: Preset | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    timezone: str = "UTC",
    now: datetime | None = None,
) -> ResolvedTimeRange:
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise _invalid(f"Unknown IANA timezone: {timezone}") from exc

    explicit = start is not None or end is not None
    if days is not None and (preset is not None or explicit):
        raise _invalid("Use either legacy days, a preset, or start/end—not a combination")
    if preset is not None and explicit:
        raise _invalid("Use either a preset or start/end—not both")
    if explicit and (start is None or end is None):
        raise _invalid("Custom ranges require both start and end")

    current = (now or datetime.now(UTC)).astimezone(UTC)
    if explicit:
        assert start is not None and end is not None
        local_start = start.replace(tzinfo=zone) if start.tzinfo is None else start
        local_end = end.replace(tzinfo=zone) if end.tzinfo is None else end
        start_utc = local_start.astimezone(UTC)
        end_utc = local_end.astimezone(UTC)
        semantics: Literal["rolling_duration", "custom_calendar"] = "custom_calendar"
        legacy_days = None
    else:
        duration = days if days is not None else PRESET_DAYS.get(preset or "30d", 30)
        if not 1 <= duration <= 365:
            raise _invalid("days must be between 1 and 365")
        end_utc = current
        start_utc = current - timedelta(days=duration)
        semantics = "rolling_duration"
        legacy_days = days

    if start_utc >= end_utc:
        raise _invalid("start must be before end")
    seconds = (end_utc - start_utc).total_seconds()
    if seconds > 365 * 86400:
        raise _invalid("Time ranges may not exceed 365 days")
    return ResolvedTimeRange(
        start=start_utc.isoformat(),
        end=end_utc.isoformat(),
        prior_start=(start_utc - (end_utc - start_utc)).isoformat(),
        prior_end=start_utc.isoformat(),
        timezone=timezone,
        preset=preset,
        legacy_days=legacy_days,
        semantics=semantics,
        duration_days=max(1, ceil(seconds / 86400)),
    )


def resolve_time_range(
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    preset: Annotated[Preset | None, Query()] = None,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    timezone: Annotated[str, Query(min_length=1, max_length=64)] = "UTC",
) -> ResolvedTimeRange:
    return resolve_values(days=days, preset=preset, start=start, end=end, timezone=timezone)


def resolve_optional_time_range(
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    preset: Annotated[Preset | None, Query()] = None,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    timezone: Annotated[str, Query(min_length=1, max_length=64)] = "UTC",
) -> ResolvedTimeRange | None:
    if days is None and preset is None and start is None and end is None:
        return None
    return resolve_values(days=days, preset=preset, start=start, end=end, timezone=timezone)
