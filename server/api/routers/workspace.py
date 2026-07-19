"""Workspace API router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime, get_workspace_id
from server.api.payloads import build_workspace
from server.api.schemas import CollectionStatus, WorkspaceResponse

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("", response_model=WorkspaceResponse)
def workspace(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
) -> WorkspaceResponse:
    runtime_info = runtime.pipeline.collection_runtime
    collection = CollectionStatus(
        mode=runtime_info.mode,
        label=runtime_info.label,
        auto_sync_active=runtime_info.watcher_enabled or runtime_info.refresh_enabled,
        watcher_enabled=runtime_info.watcher_enabled,
        refresh_enabled=runtime_info.refresh_enabled,
        poll_interval_sec=runtime_info.poll_interval_sec,
        refresh_interval_sec=runtime_info.refresh_interval_sec,
        limitation=runtime_info.limitation,
    )
    return build_workspace(
        runtime.database.reader,
        workspace_id=workspace_id,
        root_path=str(runtime.workspace_root),
        collection=collection,
    )
