"""Traces API router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime, get_workspace_id
from server.api.payloads import (
    build_replay,
    build_replay_checkpoints,
    build_trace_detail,
    build_traces_list,
)
from server.api.schemas import ReplayResponse, TraceDetailResponse, TracesListResponse

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("", response_model=TracesListResponse)
def list_traces(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    days: int | None = None,
    source: str | None = None,
    project: str | None = None,
    actor: str | None = None,
    q: str | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> TracesListResponse:
    del sort  # reserved for future sort keys
    return build_traces_list(
        runtime.database.reader,
        workspace_id=workspace_id,
        days=days,
        source=source,
        project=project,
        actor=actor,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/{trace_id}", response_model=TraceDetailResponse)
def get_trace(
    trace_id: str,
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
) -> TraceDetailResponse:
    detail = build_trace_detail(runtime.database.reader, trace_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Trace {trace_id} not found"}},
        )
    return detail


@router.get("/{trace_id}/replay", response_model=ReplayResponse)
def replay_trace(
    trace_id: str,
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    seq: int | None = None,
) -> ReplayResponse:
    if seq is None:
        replay = build_replay_checkpoints(runtime.database.reader, trace_id)
    else:
        replay = build_replay(runtime.database.reader, trace_id, seq)
    if replay is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Trace {trace_id} not found"}},
        )
    return replay
