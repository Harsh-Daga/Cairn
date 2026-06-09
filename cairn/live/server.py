"""Local HTTP server with SSE for live capture sessions."""

from __future__ import annotations

import json
import mimetypes
import re
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter
from cairn.render.capture_bundle import capture_bundle_from_project
from cairn.render.html import render_live_shell
from cairn.util.canonical import canonical_json

_SESSION_RE = re.compile(r"^/session/([^/]+)(?:/(data\.json|events))?$")
_ASSET_NAMES = frozenset({"app.js", "app.css", "capture.js"})
_ASSETS_PKG = "cairn.render.assets"


class LiveServer:
    """Serve capture bundle HTML and SSE updates for one project."""

    def __init__(self, project_root: Path, *, host: str = "127.0.0.1", port: int = 8787) -> None:
        self.project_root = resolve_git_root(project_root) or project_root.resolve()
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
        if path == "/":
            self._write_text(handler, HTTPStatus.OK, _index_html(self.base_url), "text/html")
            return

        if path.startswith("/assets/"):
            name = path.rsplit("/", 1)[-1]
            if name in _ASSET_NAMES:
                self._serve_asset(handler, name)
            else:
                self._write_text(handler, HTTPStatus.NOT_FOUND, "not found", "text/plain")
            return

        match = _SESSION_RE.match(path)
        if match is None:
            self._write_text(handler, HTTPStatus.NOT_FOUND, "not found", "text/plain")
            return

        session_id = match.group(1)
        suffix = match.group(2)
        if suffix is None:
            if not self._session_exists(session_id):
                self._write_text(handler, HTTPStatus.NOT_FOUND, "session not found", "text/plain")
                return
            html = render_live_shell(session_id)
            self._write_text(handler, HTTPStatus.OK, html, "text/html; charset=utf-8")
            return
        if suffix == "data.json":
            try:
                payload = capture_bundle_from_project(self.project_root, session_id)
            except FileNotFoundError:
                self._write_text(handler, HTTPStatus.NOT_FOUND, "session not found", "text/plain")
                return
            body = canonical_json(payload) + "\n"
            self._write_text(handler, HTTPStatus.OK, body, "application/json; charset=utf-8")
            return
        if suffix == "events":
            self._stream_events(handler, session_id)

    def _session_exists(self, session_id: str) -> bool:
        writer = CaptureWriter(self.project_root)
        try:
            return writer.load_session_by_external_id(session_id) is not None
        finally:
            writer.close()

    def _stream_events(self, handler: BaseHTTPRequestHandler, session_id: str) -> None:
        writer = CaptureWriter(self.project_root)
        try:
            summary = writer.load_session_by_external_id(session_id)
            if summary is None:
                self._write_text(handler, HTTPStatus.NOT_FOUND, "session not found", "text/plain")
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
            summary = writer.load_session_by_external_id(session_id)
            if summary is None:
                return
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
    def _serve_asset(handler: BaseHTTPRequestHandler, name: str) -> None:
        pkg = resources.files(_ASSETS_PKG)
        src = pkg / name
        with resources.as_file(src) as src_path:
            body = src_path.read_bytes()
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    @staticmethod
    def _write_text(
        handler: BaseHTTPRequestHandler,
        status: HTTPStatus,
        body: str,
        content_type: str,
    ) -> None:
        encoded = body.encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)


def _sse_frame(event: str, data: dict[str, Any]) -> bytes:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode()


def _index_html(base_url: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Cairn Live</title></head>
<body>
  <h1>Cairn Live</h1>
  <p>Open <code>{base_url}/session/&lt;session_id&gt;</code> for a capture session.</p>
</body>
</html>
"""
