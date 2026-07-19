"""Resolved half-open UTC time-range contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ResolvedTimeRange(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: str
    end: str
    prior_start: str
    prior_end: str
    timezone: str
    preset: Literal["24h", "7d", "30d", "90d"] | None
    legacy_days: int | None
    semantics: Literal["rolling_duration", "custom_calendar"]
    duration_days: int
