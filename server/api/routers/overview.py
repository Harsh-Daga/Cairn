"""Overview API router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime, get_workspace_id
from server.api.payloads import build_overview
from server.api.schemas import OverviewResponse

router = APIRouter(tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
def overview(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    days: int = 30,
) -> OverviewResponse:
    return build_overview(runtime.database.reader, workspace_id=workspace_id, days=days)
