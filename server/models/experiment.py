"""Experiment domain model (Phase 1)."""

from pydantic import BaseModel


class ExperimentSummary(BaseModel):
    """Minimal experiment summary for scaffold."""

    experiment_id: str
    status: str
