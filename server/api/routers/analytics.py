"""Analytics API router — agents, behavior, quality, usage, regions, waste, tail."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends

from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime, get_workspace_id
from server.api.payloads import (
    build_agents,
    build_behavior,
    build_budget_analytics,
    build_compare_analytics,
    build_files_analytics,
    build_guard_analytics,
    build_quality,
    build_regions_analytics,
    build_tail_analytics,
    build_tools_analytics,
    build_usage_analytics,
    build_waste_analytics,
)
from server.api.schemas import (
    AgentsResponse,
    BehaviorResponse,
    BudgetBurnResponse,
    CompareAnalyticsResponse,
    FilesAnalyticsResponse,
    GuardAnalyticsResponse,
    QualityResponse,
    RegionsAnalyticsResponse,
    TailAnalyticsResponse,
    ToolsAnalyticsResponse,
    UsageAnalyticsResponse,
    WasteAnalyticsResponse,
)
from server.api.time_range import resolve_time_range
from server.configuration import load_config
from server.models.time_range import ResolvedTimeRange

router = APIRouter(tags=["analytics"])


@router.get("/agents", response_model=AgentsResponse)
def agents(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
) -> AgentsResponse:
    return build_agents(runtime.database.reader, workspace_id=workspace_id, time_range=time_range)


@router.get("/behavior", response_model=BehaviorResponse)
def behavior(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
) -> BehaviorResponse:
    return build_behavior(runtime.database.reader, workspace_id=workspace_id, time_range=time_range)


@router.get("/quality", response_model=QualityResponse)
def quality(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
) -> QualityResponse:
    return build_quality(runtime.database.reader, workspace_id=workspace_id, time_range=time_range)


@router.get("/analytics/usage", response_model=UsageAnalyticsResponse)
def analytics_usage(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
    group_by: Literal["day", "model", "source", "project", "actor"] = "day",
) -> UsageAnalyticsResponse:
    return build_usage_analytics(
        runtime.database.reader,
        workspace_id=workspace_id,
        time_range=time_range,
        group_by=group_by,
    )


@router.get("/analytics/regions", response_model=RegionsAnalyticsResponse)
def analytics_regions(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
) -> RegionsAnalyticsResponse:
    return build_regions_analytics(
        runtime.database.reader, workspace_id=workspace_id, time_range=time_range
    )


@router.get("/analytics/waste", response_model=WasteAnalyticsResponse)
def analytics_waste(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
) -> WasteAnalyticsResponse:
    return build_waste_analytics(
        runtime.database.reader, workspace_id=workspace_id, time_range=time_range
    )


@router.get("/analytics/tools", response_model=ToolsAnalyticsResponse)
def analytics_tools(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
) -> ToolsAnalyticsResponse:
    return build_tools_analytics(
        runtime.database.reader, workspace_id=workspace_id, time_range=time_range
    )


@router.get("/analytics/files", response_model=FilesAnalyticsResponse)
def analytics_files(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
) -> FilesAnalyticsResponse:
    return build_files_analytics(
        runtime.database.reader, workspace_id=workspace_id, time_range=time_range
    )


@router.get("/analytics/compare", response_model=CompareAnalyticsResponse)
def analytics_compare(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
) -> CompareAnalyticsResponse:
    return build_compare_analytics(
        runtime.database.reader, workspace_id=workspace_id, time_range=time_range
    )


@router.get("/analytics/guard", response_model=GuardAnalyticsResponse)
def analytics_guard(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
) -> GuardAnalyticsResponse:
    return build_guard_analytics(
        runtime.database.reader,
        workspace_id=workspace_id,
        workspace_root=runtime.workspace_root,
        time_range=time_range,
    )


@router.get("/analytics/budget", response_model=BudgetBurnResponse)
def analytics_budget(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
) -> BudgetBurnResponse:
    budgets = load_config(runtime.workspace_root).budgets
    return build_budget_analytics(
        runtime.database.reader,
        workspace_id=workspace_id,
        monthly_limit_usd=budgets.monthly_usd,
        weekly_limit_usd=budgets.weekly_usd,
        daily_limit_usd=budgets.daily_usd,
        timezone=time_range.timezone,
    )


@router.get("/analytics/tail", response_model=TailAnalyticsResponse)
def analytics_tail(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange, Depends(resolve_time_range)],
) -> TailAnalyticsResponse:
    return build_tail_analytics(
        runtime.database.reader, workspace_id=workspace_id, time_range=time_range
    )
