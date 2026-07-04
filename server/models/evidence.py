"""Evidence provenance model (Phase 1)."""

from pydantic import BaseModel


class Evidence(BaseModel):
    """Machine-readable evidence reference."""

    evidence_id: str
    producer: str
    trace_ids: list[str]
