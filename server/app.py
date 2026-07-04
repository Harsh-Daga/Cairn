"""FastAPI application factory."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from server.api.bootstrap import bootstrap_runtime
from server.api.routers import ALL_ROUTERS
from server.api.sse import EventBus, sse_stream
from server.config import Settings, get_settings
from server.ingest.otlp import OtlpReceiver

API_PREFIX = "/api"


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings: Settings = application.state.settings
    runtime = bootstrap_runtime(settings)
    application.state.runtime = runtime
    application.state.database = runtime.database
    application.state.workspace_id = runtime.workspace_id
    application.state.event_bus = runtime.event_bus
    yield
    runtime.database.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    cfg = settings or get_settings()
    cfg.validate_bind()

    application = FastAPI(
        title="Cairn",
        description="Local-first observability for AI coding agents",
        version="0.1.0",
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        lifespan=_lifespan,
    )
    application.state.settings = cfg
    application.state.event_bus = EventBus()

    @application.get(f"{API_PREFIX}/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "version": "0.1.0"})

    @application.get(f"{API_PREFIX}/live/events")
    def legacy_live_events(request: Request) -> StreamingResponse:
        bus: EventBus = request.app.state.event_bus
        runtime = getattr(request.app.state, "runtime", None)
        if runtime is not None:
            bus = runtime.event_bus
        return StreamingResponse(sse_stream(bus), media_type="text/event-stream")

    for router in ALL_ROUTERS:
        application.include_router(router, prefix=API_PREFIX)

    @application.post("/v1/traces")
    async def otlp_traces(request: Request) -> JSONResponse:
        body = await request.body()
        if not body:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "empty_body", "message": "Expected OTLP/JSON body"}},
            )
        runtime = getattr(application.state, "runtime", None)
        if runtime is None:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "no_workspace", "message": "Workspace not initialized"}},
            )
        receiver = OtlpReceiver(runtime.database, runtime.workspace_id, runtime.event_bus)
        try:
            results = receiver.ingest_bytes(body)
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError, ValueError) as exc:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "invalid_otlp", "message": str(exc)}},
            )
        return JSONResponse(
            {
                "partialSuccess": {},
                "results": [
                    {
                        "trace_id": item.trace_id,
                        "inserted": item.inserted,
                        "span_count": item.span_count,
                    }
                    for item in results
                ],
            }
        )

    static_dir = cfg.static_dir
    if static_dir.is_dir():
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            application.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        index_html = static_dir / "index.html"

        @application.get("/{full_path:path}", response_model=None)
        def spa_fallback(full_path: str) -> FileResponse | JSONResponse:
            if full_path.startswith("api/"):
                return JSONResponse(
                    status_code=404,
                    content={"error": {"code": "not_found", "message": "API route not found"}},
                )
            if index_html.is_file():
                return FileResponse(index_html)
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "ui_not_built",
                        "message": "UI not built — run scripts/build_ui.py",
                    }
                },
            )

    return application


def static_exists() -> bool:
    """Check whether built UI assets are present."""
    static_dir = Path(__file__).parent / "static"
    return (static_dir / "index.html").is_file()
