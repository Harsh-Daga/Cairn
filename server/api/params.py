"""Shared bounded HTTP parameter contracts."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query

Days = Annotated[int, Query(ge=1, le=365, description="Rolling UTC duration in days")]
OptionalDays = Annotated[int | None, Query(ge=1, le=365)]
PageLimit = Annotated[int, Query(ge=1, le=200)]
PageOffset = Annotated[int, Query(ge=0, le=1_000_000)]
SearchText = Annotated[str, Query(max_length=500)]
FilterText = Annotated[str | None, Query(max_length=200)]
OptionalState = Annotated[str | None, Query(max_length=40)]
ReplaySequence = Annotated[int | None, Query(ge=0, le=10_000_000)]
