"""Workspace API router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime, get_workspace_id
from server.api.payloads import build_workspace
from server.api.schemas import WorkspaceResponse

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("", response_model=WorkspaceResponse)
def workspace(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
) -> WorkspaceResponse:
    return build_workspace(
        runtime.database.reader,
        workspace_id=workspace_id,
        root_path=str(runtime.workspace_root),
    )
