"""Insight domain model (Phase 1)."""

from pydantic import BaseModel


class InsightSummary(BaseModel):
    """Minimal insight summary for scaffold."""

    insight_id: str
    title: str
    severity: str
