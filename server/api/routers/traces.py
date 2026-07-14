"""Traces API router."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException

from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime, get_workspace_id
from server.api.payloads import (
    build_replay,
    build_replay_checkpoints,
    build_trace_detail,
    build_trace_diff,
    build_traces_list,
)
from server.api.schemas import (
    HumanLabelRequest,
    HumanLabelResponse,
    ReplayResponse,
    TraceDetailResponse,
    TraceDiffResponse,
    TracesListResponse,
)
from server.models.outcome import Outcome
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.traces import TraceRepo

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("", response_model=TracesListResponse)
def list_traces(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    days: int | None = None,
    source: str | None = None,
    project: str | None = None,
    actor: str | None = None,
    agent: str | None = None,
    q: str | None = None,
    sort: Literal["recent", "waste", "cost"] = "recent",
    limit: int = 50,
    offset: int = 0,
) -> TracesListResponse:
    return build_traces_list(
        runtime.database.reader,
        workspace_id=workspace_id,
        days=days,
        source=source,
        project=project,
        actor=actor,
        agent=agent,
        q=q,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/diff", response_model=TraceDiffResponse)
def diff_traces(
    a: str,
    b: str,
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
) -> TraceDiffResponse:
    payload = build_trace_diff(runtime.database.reader, a, b)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "One or both traces not found"}},
        )
    return payload


@router.put("/{trace_id}/human-label", response_model=HumanLabelResponse)
def set_human_label(
    trace_id: str,
    body: HumanLabelRequest,
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
) -> HumanLabelResponse:
    if TraceRepo.get(runtime.database.reader, trace_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Trace {trace_id} not found"}},
        )
    existing = OutcomeRepo.get(runtime.database.reader, trace_id) or Outcome(trace_id=trace_id)
    labeled_at = datetime.now(UTC).isoformat() if body.label is not None else None
    updated = existing.model_copy(
        update={
            "human_label": body.label,
            "human_note": body.note.strip() if body.label is not None and body.note else None,
            "human_labeled_at": labeled_at,
        }
    )
    OutcomeRepo.upsert(runtime.database.reader, updated)
    runtime.database.reader.commit()
    return HumanLabelResponse(
        trace_id=trace_id,
        label=body.label,
        note=updated.human_note,
        labeled_at=labeled_at,
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
