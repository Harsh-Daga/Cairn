"""Search API router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime, get_workspace_id
from server.api.payloads import build_search
from server.api.schemas import SearchResponse

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search(
    runtime: Annotated[AppRuntime, Depends(get_runtime)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    q: str = "",
    limit: int = 20,
) -> SearchResponse:
    return build_search(runtime.database.reader, workspace_id=workspace_id, q=q, limit=limit)
