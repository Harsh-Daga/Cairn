"""Workspace and database bootstrap for the API server."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from server.api.jobs import JobRunner
from server.api.sse import EventBus
from server.config import Settings
from server.configuration import load_config
from server.ingest.pipeline import IngestPipeline
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid


@dataclass(slots=True)
class AppRuntime:
    """Mutable server runtime attached to FastAPI app.state."""

    database: Database
    workspace_id: str
    workspace_root: Path
    event_bus: EventBus
    pipeline: IngestPipeline
    jobs: JobRunner


def resolve_workspace_root(settings: Settings) -> Path:
    """Pick active workspace root from settings or cwd."""
    if settings.workspace_root is not None:
        return settings.workspace_root.resolve()
    return Path.cwd().resolve()


def bootstrap_runtime(settings: Settings) -> AppRuntime:
    """Open DB, ensure workspace row, and wire ingest pipeline."""
    root = resolve_workspace_root(settings)
    db_path = root / ".cairn" / "cairn.db"
    database = Database(db_path)
    bus = EventBus()

    existing = WorkspaceRepo.get_by_root_path(database.reader, str(root))
    if existing is None:
        workspace_id = new_ulid()
        WorkspaceRepo.create(
            database.reader,
            Workspace(
                workspace_id=workspace_id,
                root_path=str(root),
                name=root.name,
                created_at=datetime.now(UTC).isoformat(),
            ),
        )
        database.reader.commit()
    else:
        workspace_id = existing.workspace_id

    pipeline = IngestPipeline(database, workspace_id, root, bus)
    jobs_cfg = load_config(root).jobs
    jobs = JobRunner(
        database,
        bus,
        max_workers=jobs_cfg.max_workers,
        max_queued=jobs_cfg.max_queued,
        result_ttl_sec=float(jobs_cfg.result_ttl_sec),
        default_timeout_sec=(
            float(jobs_cfg.default_timeout_sec)
            if jobs_cfg.default_timeout_sec is not None
            else None
        ),
    )
    return AppRuntime(
        database=database,
        workspace_id=workspace_id,
        workspace_root=root,
        event_bus=bus,
        pipeline=pipeline,
        jobs=jobs,
    )
