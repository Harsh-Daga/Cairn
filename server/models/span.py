"""Span domain model (Phase 1)."""

from pydantic import BaseModel


class SpanSummary(BaseModel):
    """Minimal span summary for scaffold."""

    span_id: str
    trace_id: str
    kind: str
