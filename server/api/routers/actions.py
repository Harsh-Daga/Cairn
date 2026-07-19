"""Actions API router."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from server.api.actions import build_manifest, get_action
from server.api.context import ActionCtx
from server.api.deps import get_action_ctx
from server.api.jobs import JobSaturatedError
from server.api.schemas import ActionResultResponse, ActionsManifestResponse

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("", response_model=ActionsManifestResponse)
def actions_manifest() -> ActionsManifestResponse:
    return ActionsManifestResponse(actions=build_manifest())


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    ctx: Annotated[ActionCtx, Depends(get_action_ctx)],
) -> dict[str, Any]:
    record = ctx.jobs.get(job_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Job {job_id} not found"}},
        )
    return {
        "job_id": record.job_id,
        "action": record.action,
        "status": record.status,
        "progress": record.progress,
        "message": record.message,
        "error": record.error,
        "result": record.result,
        "created_at": record.created_at,
        "finished_at": record.finished_at,
    }


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    ctx: Annotated[ActionCtx, Depends(get_action_ctx)],
) -> dict[str, Any]:
    record = ctx.jobs.cancel(job_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Job {job_id} not found"}},
        )
    return {
        "job_id": record.job_id,
        "status": record.status,
        "message": record.message,
    }


@router.post("/{name}", response_model=ActionResultResponse)
def run_action(
    name: str,
    ctx: Annotated[ActionCtx, Depends(get_action_ctx)],
    body: dict[str, Any] | None = None,
) -> ActionResultResponse:
    action_def = get_action(name)
    if action_def is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "unknown_action", "message": f"Unknown action: {name}"}},
        )
    payload = body or {}
    try:
        params = action_def.params_model.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 — return validation to client
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "invalid_params", "message": str(exc)}},
        ) from exc

    if action_def.async_job:

        def _job(progress: Callable[[float, str], None]) -> dict[str, Any]:
            progress(0.1, "starting")
            result = action_def.handler(params, ctx)
            progress(1.0, "done")
            return result

        # One active sync/backfill per action name (workspace-scoped runner).
        dedupe = action_def.name if action_def.name in {"sync", "backfill"} else None
        try:
            job_id = ctx.jobs.submit(action_def.name, _job, dedupe_key=dedupe)
        except JobSaturatedError as exc:
            raise HTTPException(
                status_code=429,
                detail={"error": {"code": "job_saturated", "message": str(exc)}},
            ) from exc
        return ActionResultResponse(ok=True, job_id=job_id)

    try:
        result = action_def.handler(params, ctx)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "action_failed", "message": str(exc)}},
        ) from exc
    return ActionResultResponse(ok=True, result=result)
