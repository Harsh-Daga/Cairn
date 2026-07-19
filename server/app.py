"""FastAPI application factory."""

from __future__ import annotations

import ipaddress
import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint

from server import __version__
from server.api.bootstrap import bootstrap_runtime
from server.api.routers import ALL_ROUTERS
from server.api.schemas import ErrorResponse
from server.config import Settings, get_settings
from server.configuration import load_config
from server.ingest.otlp import OtlpReceiver
from server.util.runtime_state import register_server, unregister_server

API_PREFIX = "/api"
MAX_OTLP_BODY_BYTES = 16 * 1024 * 1024
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
WILDCARD_HOSTS = frozenset({"0.0.0.0", "::"})
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; img-src 'self' data:; connect-src 'self'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def _hostname(authority: str) -> str | None:
    """Return a normalized hostname from a Host header or URL authority."""
    if not authority or any(char in authority for char in "\r\n\t /\\"):
        return None
    try:
        return urlsplit(f"//{authority}").hostname
    except ValueError:
        return None


def _host_allowed(request: Request, configured_host: str) -> bool:
    """Reject arbitrary DNS names while supporting loopback and explicit binds."""
    hostname = _hostname(request.headers.get("host", ""))
    if hostname is None:
        return False
    hostname = hostname.lower().rstrip(".")

    # Starlette's in-process transport has no network-facing Host boundary.
    if request.client and request.client.host == "testclient" and hostname == "testserver":
        return True
    if configured_host in WILDCARD_HOSTS:
        if hostname == "localhost":
            return True
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            return False
        return True
    allowed = {configured_host.lower().rstrip(".")}
    if configured_host in LOOPBACK_HOSTS:
        allowed.update(LOOPBACK_HOSTS)
    return hostname in allowed


def _same_origin(request: Request, origin: str) -> bool:
    """Accept only an exact HTTP(S) origin match for browser-originated requests."""
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return parsed.netloc.lower() == request.headers.get("host", "").lower()


def _secure(response: Response, request: Request) -> Response:
    """Apply local-app browser hardening and prevent sensitive API caching."""
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if request.url.path.startswith((API_PREFIX, "/v1/")):
        response.headers.setdefault("Cache-Control", "no-store")
    origin = request.headers.get("origin")
    if origin and _same_origin(request, origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    return response


def _operation_id(route: APIRoute) -> str:
    """Use concise function names as the reviewed public operation-ID contract."""
    return route.name


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings: Settings = application.state.settings
    runtime = bootstrap_runtime(settings)
    application.state.runtime = runtime
    application.state.database = runtime.database
    application.state.workspace_id = runtime.workspace_id
    application.state.event_bus = runtime.event_bus
    collection_mode = load_config(runtime.workspace_root).collection.mode
    runtime.pipeline.apply_collection_mode(collection_mode)
    register_server(
        host=settings.host,
        port=settings.port,
        workspace=settings.workspace_root,
    )
    yield
    unregister_server(settings.port)
    runtime.pipeline.stop()
    runtime.jobs.shutdown(wait=True, cancel_pending=True)
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
        generate_unique_id_function=_operation_id,
        responses={
            400: {"model": ErrorResponse, "description": "Invalid request or Host boundary"},
            401: {"model": ErrorResponse, "description": "Authentication required"},
            403: {"model": ErrorResponse, "description": "Origin or authorization denied"},
            404: {"model": ErrorResponse, "description": "Resource not found"},
            413: {"model": ErrorResponse, "description": "Request body exceeds its bound"},
            422: {"model": ErrorResponse, "description": "Request validation failed"},
        },
    )
    application.state.settings = cfg

    @application.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Return one public application-error envelope."""
        detail = cast(object, exc.detail)
        if isinstance(detail, dict) and isinstance(detail.get("error"), dict):
            error = dict(detail["error"])
        else:
            error = {
                "code": "http_error",
                "message": str(detail) if detail else "Request failed",
            }
        return JSONResponse(status_code=exc.status_code, content={"error": error})

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "location": [str(part) for part in item["loc"]],
                "message": item["msg"],
                "type": item["type"],
            }
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request parameters are invalid",
                    "details": details,
                }
            },
        )

    @application.middleware("http")
    async def protect_local_service(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Enforce the local browser boundary and optional bearer authentication."""
        if not _host_allowed(request, cfg.host):
            return _secure(
                JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "invalid_host",
                            "message": "Host is not allowed for this Cairn server",
                        }
                    },
                ),
                request,
            )

        origin = request.headers.get("origin")
        if origin and not _same_origin(request, origin):
            return _secure(
                JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "invalid_origin",
                            "message": "Cross-origin browser requests are not allowed",
                        }
                    },
                ),
                request,
            )
        if request.method == "OPTIONS":
            response = Response(status_code=204)
            response.headers["Access-Control-Allow-Methods"] = "GET, HEAD, POST, PUT, PATCH, DELETE"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response.headers["Access-Control-Max-Age"] = "600"
            return _secure(response, request)

        if not cfg.token:
            return _secure(await call_next(request), request)

        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        supplied = supplied or request.cookies.get("cairn_token", "")
        query_token = request.query_params.get("token")
        if (
            request.method in {"GET", "HEAD"}
            and query_token
            and secrets.compare_digest(query_token, cfg.token)
        ):
            params = [
                (key, value) for key, value in request.query_params.multi_items() if key != "token"
            ]
            location = request.url.path
            if params:
                location = f"{location}?{urlencode(params)}"
            response = RedirectResponse(location, status_code=307)
            response.headers["Cache-Control"] = "no-store"
            response.set_cookie(
                "cairn_token",
                cfg.token,
                httponly=True,
                samesite="strict",
                secure=request.url.scheme == "https",
            )
            return _secure(response, request)
        if supplied and secrets.compare_digest(supplied, cfg.token):
            return _secure(await call_next(request), request)
        return _secure(
            JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "unauthorized",
                        "message": "Valid Cairn token required",
                    }
                },
                headers={"WWW-Authenticate": "Bearer"},
            ),
            request,
        )

    @application.get(f"{API_PREFIX}/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok", "version": __version__})

    for router in ALL_ROUTERS:
        application.include_router(router, prefix=API_PREFIX)

    @application.post("/v1/traces")
    async def otlp_traces(request: Request) -> JSONResponse:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = -1
            if declared_size < 0 or declared_size > MAX_OTLP_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "payload_too_large",
                            "message": f"OTLP body must be at most {MAX_OTLP_BODY_BYTES} bytes",
                        }
                    },
                )
        body = await request.body()
        if len(body) > MAX_OTLP_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "payload_too_large",
                        "message": f"OTLP body must be at most {MAX_OTLP_BODY_BYTES} bytes",
                    }
                },
            )
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
            # Never cache the SPA shell — hashed asset URLs change on each UI build.
            return FileResponse(
                index_html,
                headers={"Cache-Control": "no-store"},
            )
        return HTMLResponse(_DEV_BUILD_HTML, status_code=503)

    return application


def static_exists() -> bool:
    """Check whether built UI assets are present."""
    static_dir = Path(__file__).parent / "static"
    return (static_dir / "index.html").is_file()
