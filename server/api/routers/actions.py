"""Actions API router."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from server.api.actions import build_manifest, get_action
from server.api.context import ActionCtx
from server.api.deps import get_action_ctx
from server.api.schemas import ActionResultResponse, ActionsManifestResponse

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("", response_model=ActionsManifestResponse)
def actions_manifest() -> ActionsManifestResponse:
    return ActionsManifestResponse(actions=build_manifest())


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

        job_id = ctx.jobs.submit(action_def.name, _job)
        return ActionResultResponse(ok=True, job_id=job_id)

    try:
        result = action_def.handler(params, ctx)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "action_failed", "message": str(exc)}},
        ) from exc
    return ActionResultResponse(ok=True, result=result)
