"""Trace domain model (Phase 1)."""

from pydantic import BaseModel


class TraceSummary(BaseModel):
    """Minimal trace summary for scaffold."""

    trace_id: str
    source: str
    title: str | None = None
