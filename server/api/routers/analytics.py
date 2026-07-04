"""Analytics API router — agents, behavior, quality, usage, regions, waste, tail."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime, get_workspace_id
from server.api.payloads import (
    build_agents,
    build_behavior,
    build_quality,
    build_regions_analytics,
    build_tail_analytics,
    build_usage_analytics,
    build_waste_analytics,
)
from server.api.schemas import (
    AgentsResponse,
    BehaviorResponse,
    QualityResponse,
    RegionsAnalyticsResponse,
    TailAnalyticsResponse,
    UsageAnalyticsResponse,
    WasteAnalyticsResponse,
)

router = APIRouter(tags=["analytics"])


@router.get("/agents", response_model=AgentsResponse)
def agents(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    days: int = 30,
) -> AgentsResponse:
    return build_agents(runtime.database.reader, workspace_id=workspace_id, days=days)


@router.get("/behavior", response_model=BehaviorResponse)
def behavior(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    days: int = 30,
) -> BehaviorResponse:
    return build_behavior(runtime.database.reader, workspace_id=workspace_id, days=days)


@router.get("/quality", response_model=QualityResponse)
def quality(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    days: int = 30,
) -> QualityResponse:
    return build_quality(runtime.database.reader, workspace_id=workspace_id, days=days)


@router.get("/analytics/usage", response_model=UsageAnalyticsResponse)
def analytics_usage(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    days: int = 30,
    group_by: Literal["day", "model", "source", "project", "actor"] = "day",
) -> UsageAnalyticsResponse:
    return build_usage_analytics(
        runtime.database.reader,
        workspace_id=workspace_id,
        days=days,
        group_by=group_by,
    )


@router.get("/analytics/regions", response_model=RegionsAnalyticsResponse)
def analytics_regions(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    days: int = 30,
) -> RegionsAnalyticsResponse:
    return build_regions_analytics(runtime.database.reader, workspace_id=workspace_id, days=days)


@router.get("/analytics/waste", response_model=WasteAnalyticsResponse)
def analytics_waste(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    days: int = 30,
) -> WasteAnalyticsResponse:
    return build_waste_analytics(runtime.database.reader, workspace_id=workspace_id, days=days)


@router.get("/analytics/tail", response_model=TailAnalyticsResponse)
def analytics_tail(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    days: int = 30,
) -> TailAnalyticsResponse:
    return build_tail_analytics(runtime.database.reader, workspace_id=workspace_id, days=days)
