"""Action execution context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from server.api.jobs import JobRunner
from server.api.sse import EventBus
from server.ingest.pipeline import IngestPipeline
from server.store.db import Database


@dataclass(slots=True)
class ActionCtx:
    """Shared context passed to every registered action handler."""

    db: Database
    workspace_id: str
    workspace_root: Path
    event_bus: EventBus
    pipeline: IngestPipeline
    jobs: JobRunner
