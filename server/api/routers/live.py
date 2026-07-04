"""Live SSE API router."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from server.api.bootstrap import AppRuntime
from server.api.deps import get_runtime
from server.api.sse import sse_stream

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/events")
def live_events(runtime: Annotated[AppRuntime, Depends(get_runtime)]) -> StreamingResponse:
    return StreamingResponse(sse_stream(runtime.event_bus), media_type="text/event-stream")
