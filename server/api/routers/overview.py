"""Overview API router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime, get_workspace_id
from server.api.payloads import build_overview, build_recap
from server.api.schemas import OverviewResponse, RecapResponse
from server.api.time_range import resolve_time_range
from server.configuration import load_config
from server.models.time_range import ResolvedTimeRange

router = APIRouter(tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
def overview(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
) -> OverviewResponse:
    budgets = load_config(runtime.workspace_root).budgets
    return build_overview(
        runtime.database.reader,
        workspace_id=workspace_id,
        time_range=time_range,
        monthly_budget_usd=budgets.monthly_usd,
        weekly_budget_usd=budgets.weekly_usd,
        daily_budget_usd=budgets.daily_usd,
        workspace_root=runtime.workspace_root,
    )


@router.get("/recap", response_model=RecapResponse)
def recap(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
) -> RecapResponse:
    return build_recap(runtime.database.reader, workspace_id=workspace_id)
