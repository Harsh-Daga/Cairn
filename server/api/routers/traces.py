"""Traces API router."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException

from server.analyze.corrections import build_corrections_for_trace
from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime, get_workspace_id
from server.api.params import FilterText, PageLimit, PageOffset, ReplaySequence
from server.api.payloads import (
    build_replay,
    build_replay_checkpoints,
    build_trace_corrections,
    build_trace_detail,
    build_trace_diff,
    build_trace_handoff,
    build_trace_receipt,
    build_traces_list,
)
from server.api.schemas import (
    CorrectionRelabelRequest,
    CorrectionsResponse,
    HandoffResponse,
    HumanLabelRequest,
    HumanLabelResponse,
    PostmortemResponse,
    ReceiptResponse,
    ReplayResponse,
    TraceDetailResponse,
    TraceDiffResponse,
    TracesListResponse,
)
from server.api.time_range import resolve_optional_time_range
from server.models.outcome import Outcome
from server.models.time_range import ResolvedTimeRange
from server.store.repos.corrections import CorrectionRepo
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.traces import TraceRepo

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("", response_model=TracesListResponse)
def list_traces(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    time_range: Annotated[ResolvedTimeRange | None, Depends(resolve_optional_time_range)],
    source: FilterText = None,
    project: FilterText = None,
    actor: FilterText = None,
    agent: FilterText = None,
    q: FilterText = None,
    sort: Literal["recent", "waste", "cost", "duration", "tokens", "quality"] = "recent",
    limit: PageLimit = 50,
    offset: PageOffset = 0,
) -> TracesListResponse:
    return build_traces_list(
        runtime.database.reader,
        workspace_id=workspace_id,
        start=time_range.start if time_range is not None else None,
        end=time_range.end if time_range is not None else None,
        time_range=time_range,
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
    workspace_id: Annotated[str, Depends(get_workspace_id)],
) -> TraceDiffResponse:
    payload = build_trace_diff(runtime.database.reader, a, b, workspace_id=workspace_id)
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
    detail = build_trace_detail(
        runtime.database.reader,
        trace_id,
        workspace_root=runtime.workspace_root,
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Trace {trace_id} not found"}},
        )
    return detail


@router.get("/{trace_id}/postmortem", response_model=PostmortemResponse)
def get_postmortem(
    trace_id: str,
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
) -> PostmortemResponse:
    detail = build_trace_detail(
        runtime.database.reader,
        trace_id,
        workspace_root=runtime.workspace_root,
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Trace {trace_id} not found"}},
        )
    if detail.postmortem is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"No postmortem for trace {trace_id}",
                }
            },
        )
    return detail.postmortem


@router.get("/{trace_id}/receipt", response_model=ReceiptResponse)
def get_receipt(
    trace_id: str,
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
) -> ReceiptResponse:
    payload = build_trace_receipt(runtime.database.reader, trace_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Trace {trace_id} not found"}},
        )
    return payload


@router.get("/{trace_id}/corrections", response_model=CorrectionsResponse)
def get_corrections(
    trace_id: str,
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
) -> CorrectionsResponse:
    payload = build_trace_corrections(runtime.database.reader, trace_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Trace {trace_id} not found"}},
        )
    return payload


@router.put(
    "/{trace_id}/corrections/{correction_id}/relabel",
    response_model=CorrectionsResponse,
)
def relabel_correction(
    trace_id: str,
    correction_id: str,
    body: CorrectionRelabelRequest,
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
) -> CorrectionsResponse:
    current = build_corrections_for_trace(runtime.database.reader, trace_id)
    if current is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Trace {trace_id} not found"}},
        )
    match = next(
        (item for item in current["corrections"] if item["correction_id"] == correction_id),
        None,
    )
    if match is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "not_found",
                    "message": f"Correction {correction_id} not found",
                }
            },
        )
    labeled_at = datetime.now(UTC).isoformat()
    original_class = str(match["original_class"])

    def _write(conn: sqlite3.Connection) -> None:
        CorrectionRepo.upsert_relabel(
            conn,
            correction_id=correction_id,
            trace_id=trace_id,
            original_class=original_class,
            relabel_class=body.relabel_class,
            note=body.note,
            labeled_at=labeled_at,
        )

    runtime.database.write(_write)
    payload = build_trace_corrections(runtime.database.reader, trace_id)
    assert payload is not None
    return payload


@router.get("/{trace_id}/handoff", response_model=HandoffResponse)
def get_handoff(
    trace_id: str,
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
) -> HandoffResponse:
    payload = build_trace_handoff(
        runtime.database.reader,
        trace_id,
        workspace_root=runtime.workspace_root,
    )
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Trace {trace_id} not found"}},
        )
    return payload


@router.get("/{trace_id}/replay", response_model=ReplayResponse)
def replay_trace(
    trace_id: str,
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    seq: ReplaySequence = None,
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
