"""FastAPI application factory."""

from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

from server import __version__
from server.api.bootstrap import bootstrap_runtime
from server.api.routers import ALL_ROUTERS
from server.config import Settings, get_settings
from server.ingest.otlp import OtlpReceiver
from server.util.runtime_state import register_server, unregister_server

API_PREFIX = "/api"


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings: Settings = application.state.settings
    runtime = bootstrap_runtime(settings)
    application.state.runtime = runtime
    application.state.database = runtime.database
    application.state.workspace_id = runtime.workspace_id
    application.state.event_bus = runtime.event_bus
    runtime.pipeline.start()
    register_server(
        host=settings.host,
        port=settings.port,
        workspace=settings.workspace_root,
    )
    yield
    unregister_server(settings.port)
    runtime.pipeline.stop()
    runtime.database.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    cfg = settings or get_settings()
    cfg.validate_bind()

    application = FastAPI(
        title="Cairn",
        description="Local-first observability for AI coding agents",
        version=__version__,
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        lifespan=_lifespan,
    )
    application.state.settings = cfg

    @application.middleware("http")
    async def require_token(request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Protect every endpoint when the server is exposed beyond loopback."""
        if not cfg.token:
            return await call_next(request)

        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        supplied = supplied or request.cookies.get("cairn_token", "")
        query_token = request.query_params.get("token")
        if query_token and secrets.compare_digest(query_token, cfg.token):
            params = [
                (key, value) for key, value in request.query_params.multi_items() if key != "token"
            ]
            location = request.url.path
            if params:
                location = f"{location}?{urlencode(params)}"
            response = RedirectResponse(location, status_code=307)
            response.set_cookie("cairn_token", cfg.token, httponly=True, samesite="lax")
            return response
        if supplied and secrets.compare_digest(supplied, cfg.token):
            return await call_next(request)
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "unauthorized", "message": "Valid Cairn token required"}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @application.get(f"{API_PREFIX}/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "version": __version__})

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
            results = receiver.ingest_bytes(body, content_type=request.headers.get("content-type"))
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
    index_html = static_dir / "index.html"
    ui_built = index_html.is_file()

    if ui_built:
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            application.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    _DEV_BUILD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Cairn — UI not built</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 42rem;
           margin: 4rem auto; padding: 0 1rem; }
    code { background: #f4f4f5; padding: 0.15rem 0.35rem; border-radius: 4px; }
    pre { background: #18181b; color: #fafafa; padding: 1rem; border-radius: 8px; }
  </style>
</head>
<body>
  <h1>Cairn dashboard UI not bundled</h1>
  <p>The API is running, but static assets are missing from this install.
     Build the UI once, then restart:</p>
  <pre>python scripts/build_ui.py
cairn ui --no-open</pre>
  <p>API health: <a href="/api/health">/api/health</a></p>
</body>
</html>"""

    @application.get("/{full_path:path}", response_model=None)
    def spa_fallback(full_path: str) -> FileResponse | HTMLResponse | JSONResponse:
        if full_path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "not_found", "message": "API route not found"}},
            )
        if ui_built:
            return FileResponse(index_html)
        return HTMLResponse(_DEV_BUILD_HTML, status_code=503)

    return application


def static_exists() -> bool:
    """Check whether built UI assets are present."""
    static_dir = Path(__file__).parent / "static"
    return (static_dir / "index.html").is_file()
