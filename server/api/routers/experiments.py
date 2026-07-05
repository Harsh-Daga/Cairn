"""Experiments API router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime
from server.api.payloads import build_experiment_detail, build_experiments
from server.api.schemas import ExperimentDetailResponse, ExperimentsResponse

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.get("", response_model=ExperimentsResponse)
def list_experiments(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
) -> ExperimentsResponse:
    return build_experiments(runtime.database.reader)


@router.get("/{experiment_id}", response_model=ExperimentDetailResponse)
def get_experiment(
    experiment_id: str,
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
) -> ExperimentDetailResponse:
    detail = build_experiment_detail(
        runtime.database.reader,
        experiment_id,
        workspace_id=runtime.workspace_id,
    )
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {"code": "not_found", "message": f"Experiment {experiment_id} not found"},
            },
        )
    return detail
