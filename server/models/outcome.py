"""Outcome domain model (Phase 1)."""

from pydantic import BaseModel


class OutcomeSummary(BaseModel):
    """Minimal outcome summary for scaffold."""

    trace_id: str
    quality_score: float | None = None
