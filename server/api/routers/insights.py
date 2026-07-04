"""Insights API router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime
from server.api.payloads import build_evidence_chain, build_insights
from server.api.schemas import EvidenceChainResponse, InsightsResponse

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("", response_model=InsightsResponse)
def list_insights(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    state: str | None = None,
    limit: int = 100,
) -> InsightsResponse:
    return build_insights(runtime.database.reader, state=state, limit=limit)


@router.get("/{insight_id}/evidence", response_model=EvidenceChainResponse)
def insight_evidence(
    insight_id: str,
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
) -> EvidenceChainResponse:
    chain = build_evidence_chain(runtime.database.reader, insight_id)
    if chain is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Insight {insight_id} not found"}},
        )
    return chain
