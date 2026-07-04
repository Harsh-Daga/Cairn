"""FastAPI dependencies and request helpers."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, HTTPException, Query, Request

from server.api.bootstrap import AppRuntime
from server.api.context import ActionCtx


def get_runtime(request: Request) -> AppRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "no_workspace", "message": "Workspace not initialized"}},
        )
    return cast(AppRuntime, runtime)


def get_workspace_id(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    ws: Annotated[str | None, Query(alias="ws")] = None,
) -> str:
    if ws is not None:
        return ws
    return runtime.workspace_id


def get_action_ctx(runtime: Annotated[AppRuntime, Depends(get_runtime)]) -> ActionCtx:
    return ActionCtx(
        db=runtime.database,
        workspace_id=runtime.workspace_id,
        workspace_root=runtime.workspace_root,
        event_bus=runtime.event_bus,
        pipeline=runtime.pipeline,
        jobs=runtime.jobs,
    )
