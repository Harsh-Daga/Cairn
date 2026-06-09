"""Local HTTP API server (Phase 17)."""

from __future__ import annotations

import json
import re
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cairn.api.openapi import openapi_spec
from cairn.cache.store import CacheStore
from cairn.cli.sessions_cmd import _session_dict
from cairn.executor.runner import BuildOptions
from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter
from cairn.providers.registry import create_provider
from cairn.report.engine import build_report, report_from_capture
from cairn.util.canonical import canonical_json
from cairn.workflow.engine import WorkflowEngine
from cairn.workflow.loader import load_workflow

_PROJECT_SESSIONS_RE = re.compile(r"^/v1/projects/([^/]+)/sessions$")
_SESSION_RE = re.compile(r"^/v1/sessions/([^/]+)$")
_SESSION_EVENTS_RE = re.compile(r"^/v1/sessions/([^/]+)/events$")
_WORKFLOW_RUN_RE = re.compile(r"^/v1/workflows/([^/]+)/run$")
_RUN_REPORT_RE = re.compile(r"^/v1/runs/([^/]+)/report$")


class ApiServer:
    """Serve the Cairn v1 HTTP API for a single project root."""

    def __init__(self, project_root: Path, *, host: str = "127.0.0.1", port: int = 8790) -> None:
        self.project_root = resolve_git_root(project_root) or project_root.resolve()
        self.project_id = self.project_root.name
        self.host = host
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def serve_forever(self) -> None:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def do_GET(self) -> None:
                server._handle_get(self)

            def do_POST(self) -> None:
                server._handle_post(self)

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._httpd.serve_forever()

    def serve_background(self) -> None:
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _handle_get(self, handler: BaseHTTPRequestHandler) -> None:
        path = urlparse(handler.path).path
        if path == "/v1/openapi.json":
            self._write_json(handler, HTTPStatus.OK, openapi_spec())
            return

        match = _PROJECT_SESSIONS_RE.match(path)
        if match is not None:
            if not self._check_project(match.group(1), handler):
                return
            self._list_sessions(handler)
            return

        match = _SESSION_RE.match(path)
        if match is not None:
            self._get_session(handler, match.group(1))
            return

        match = _SESSION_EVENTS_RE.match(path)
        if match is not None:
            self._stream_session_events(handler, match.group(1))
            return

        match = _RUN_REPORT_RE.match(path)
        if match is not None:
            self._get_run_report(handler, match.group(1))
            return

        self._write_json(handler, HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _handle_post(self, handler: BaseHTTPRequestHandler) -> None:
        path = urlparse(handler.path).path
        match = _WORKFLOW_RUN_RE.match(path)
        if match is None:
            self._write_json(handler, HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        body = _read_json_body(handler)
        self._run_workflow(handler, match.group(1), body)

    def _check_project(self, project_id: str, handler: BaseHTTPRequestHandler) -> bool:
        if project_id != self.project_id:
            self._write_json(handler, HTTPStatus.NOT_FOUND, {"error": "project not found"})
            return False
        return True

    def _list_sessions(self, handler: BaseHTTPRequestHandler) -> None:
        writer = CaptureWriter(self.project_root)
        try:
            sessions = writer.list_sessions()
            payload = {
                "project_id": self.project_id,
                "sessions": [_session_dict(s) for s in sessions],
            }
        finally:
            writer.close()
        self._write_json(handler, HTTPStatus.OK, payload)

    def _get_session(self, handler: BaseHTTPRequestHandler, session_id: str) -> None:
        writer = CaptureWriter(self.project_root)
        try:
            summary = writer.load_session_by_external_id(session_id)
            if summary is None:
                self._write_json(handler, HTTPStatus.NOT_FOUND, {"error": "session not found"})
                return
            payload = _session_dict(summary)
            trajectory = writer.load_trajectory(session_id)
            if trajectory is not None:
                payload["trajectory"] = trajectory
        finally:
            writer.close()
        self._write_json(handler, HTTPStatus.OK, payload)

    def _get_run_report(self, handler: BaseHTTPRequestHandler, run_id: str) -> None:
        writer = CaptureWriter(self.project_root)
        try:
            row = writer.connection.execute(
                "SELECT kind, external_id FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        finally:
            writer.close()
        try:
            if row is None:
                self._write_json(handler, HTTPStatus.NOT_FOUND, {"error": "run not found"})
                return
            kind = str(row["kind"])
            if kind == "capture" and row["external_id"]:
                report = report_from_capture(self.project_root, str(row["external_id"]))
            else:
                report = build_report(self.project_root, run_id=run_id)
        except (FileNotFoundError, ValueError) as exc:
            self._write_json(handler, HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        self._write_json(handler, HTTPStatus.OK, report)

    def _run_workflow(
        self,
        handler: BaseHTTPRequestHandler,
        workflow_id: str,
        body: dict[str, Any],
    ) -> None:
        try:
            project, workflow = load_workflow(self.project_root, workflow_id)
            engine = WorkflowEngine(project, workflow)
            cache = CacheStore(project.root)
            fixtures = Path(__file__).resolve().parents[1] / "data" / "fixtures"
            provider_mode = str(body.get("provider_mode", "recorded"))
            provider = create_provider(
                mode="recorded" if provider_mode == "recorded" else "live",
                fixtures_dir=fixtures,
                model=project.defaults_model,
            )
            try:
                dry_run = bool(body.get("dry_run", False))
                options = BuildOptions(
                    dry_run=dry_run,
                    yes=bool(body.get("yes", True)),
                    max_cost=body.get("max_cost"),
                )
                if dry_run:
                    result = engine.validate()
                    payload = {
                        "workflow_ref": result.workflow_ref,
                        "ok": result.ok,
                        "dry_run": True,
                        "node_count": result.node_count,
                    }
                else:
                    run_result = engine.run(cache, provider, options=options)
                    payload = {
                        "workflow_ref": run_result.workflow_ref,
                        "run_id": run_result.run_id,
                        "context_digest": run_result.context_digest,
                        "node_count": run_result.node_count,
                        "cache_hits": run_result.cache_hits,
                    }
            finally:
                cache.close()
        except Exception as exc:
            self._write_json(handler, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._write_json(handler, HTTPStatus.OK, payload)

    def _stream_session_events(self, handler: BaseHTTPRequestHandler, session_id: str) -> None:
        writer = CaptureWriter(self.project_root)
        try:
            summary = writer.load_session_by_external_id(session_id)
            if summary is None:
                self._write_json(handler, HTTPStatus.NOT_FOUND, {"error": "session not found"})
                return
        finally:
            writer.close()

        handler.close_connection = True
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.wfile.write(b": connected\n\n")
        handler.wfile.flush()

        writer = CaptureWriter(self.project_root)
        last_seq = 0
        try:
            while True:
                summary = writer.load_session_by_external_id(session_id)
                if summary is None:
                    break
                events = writer.load_events(summary.run_id)
                for event in events:
                    seq = int(event.get("seq", 0))
                    if seq <= last_seq:
                        continue
                    last_seq = seq
                    handler.wfile.write(_sse_frame("append", event))
                    handler.wfile.flush()
                if summary.status != "in_progress":
                    finish = {
                        "status": summary.status,
                        "external_id": summary.external_id,
                        "event_count": summary.event_count,
                    }
                    handler.wfile.write(_sse_frame("finish", finish))
                    handler.wfile.flush()
                    break
                time.sleep(0.25)
        finally:
            writer.close()

    @staticmethod
    def _write_json(
        handler: BaseHTTPRequestHandler,
        status: HTTPStatus,
        payload: dict[str, Any],
    ) -> None:
        body = canonical_json(payload) + "\n"
        encoded = body.encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sse_frame(event: str, data: dict[str, Any]) -> bytes:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode()
