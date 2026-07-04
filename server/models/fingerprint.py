"""Fingerprint domain model (Phase 1)."""

from pydantic import BaseModel


class FingerprintVector(BaseModel):
    """Behavioral fingerprint vector."""

    trace_id: str
    vector: list[float]
