"""Local HTTP server — dashboard + /api/* + SSE."""

from __future__ import annotations

import contextlib
import json
import mimetypes
import re
import socket
import sys
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter
from cairn.insights.engine import evaluate as evaluate_insights
from cairn.ledger.ledger import Ledger
from cairn.ledger.resolve import canonical_json
from cairn.render.dash_payload import (
    charts_payload,
    optimize_payload,
    overview_payload,
    search_payload,
    sessions_payload,
    top_files_payload,
)
from cairn.render.session_payload import session_payload

_API_OVERVIEW = re.compile(r"^/api/overview$")
_API_CHARTS = re.compile(r"^/api/charts$")
_API_SESSIONS = re.compile(r"^/api/sessions$")
_API_SESSION = re.compile(r"^/api/session/([^/]+)$")
_API_PROFILE = re.compile(r"^/api/profile/([^/]+)$")
_API_RECOVERABLE = re.compile(r"^/api/recoverable$")
_API_BEHAVIOR = re.compile(r"^/api/behavior$")
_API_OUTCOMES = re.compile(r"^/api/outcomes$")
_API_INSIGHTS = re.compile(r"^/api/insights$")
_API_OPTIMIZE = re.compile(r"^/api/optimize$")
_API_ACTION_OPTIMIZE = re.compile(r"^/api/action/optimize$")
_API_SEARCH = re.compile(r"^/api/search$")
_API_GAUGE = re.compile(r"^/api/gauge$")
_API_CONFIG = re.compile(r"^/api/config$")
_API_SETUP_SCAN = re.compile(r"^/api/setup/scan$")
_API_ACTION_SYNC = re.compile(r"^/api/action/sync$")
_API_ACTION_BACKFILL = re.compile(r"^/api/action/backfill$")
_API_ACTION_CHECK = re.compile(r"^/api/action/check$")
_API_ACTION_MCP = re.compile(r"^/api/action/mcp_install$")
_API_ACTION_MCP_AUTO = re.compile(r"^/api/action/mcp_auto_install$")
_API_ACTION_SHARE = re.compile(r"^/api/action/share$")
_API_REFRESH = re.compile(r"^/api/refresh$")
_API_ACTION = re.compile(r"^/api/action$")
_V2_EVENTS = re.compile(r"^/v2/events$")
_ASSETS_PKG = "cairn.assets"
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class LiveServer:
    def __init__(
        self,
        project_root: Path,
        *,
        host: str = "127.0.0.1",
        port: int = 8787,
    ) -> None:
        self.project_root = resolve_git_root(project_root) or project_root.resolve()
        if host not in _LOOPBACK_HOSTS:
            msg = f"cairn live server binds to loopback only (127.0.0.1/::1); got {host!r}"
            raise ValueError(msg)
        self.host = host
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._sse_lock = threading.Lock()
        self._sse_clients: list[BaseHTTPRequestHandler] = []
        self._vscdb_watcher: Any = None

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
        self.wait_until_ready()
        self._start_vscdb_watcher()

    def _start_vscdb_watcher(self) -> None:
        from cairn.config import mcp_auto_install_enabled
        from cairn.ingest.watch import VscdbWatcher, watched_vscdb_paths

        if mcp_auto_install_enabled():
            from cairn.cli.main import mcp_auto_install_clients

            with contextlib.suppress(OSError):
                mcp_auto_install_clients(self.project_root)

        paths = watched_vscdb_paths()
        if not paths:
            return

        def _on_vscdb_change() -> None:
            from cairn.ingest.backfill import recompute_rollups
            from cairn.ingest.ingest import ingest_cursor_incremental

            ingest_cursor_incremental(self.project_root)
            writer = CaptureWriter(self.project_root)
            try:
                recompute_rollups(writer, days=90)
                conn = writer.connection
                overview = overview_payload(conn, days=7, repo_name=self.project_root.name)
            finally:
                writer.close()
            self._broadcast_sse("metrics-updated", overview)

        self._vscdb_watcher = VscdbWatcher(_on_vscdb_change, paths=paths)
        self._vscdb_watcher.start()

    def _broadcast_sse(self, event: str, data: dict[str, Any]) -> None:
        payload = _sse(event, data)
        with self._sse_lock:
            dead: list[BaseHTTPRequestHandler] = []
            for handler in self._sse_clients:
                try:
                    handler.wfile.write(payload)
                    handler.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    dead.append(handler)
            for handler in dead:
                if handler in self._sse_clients:
                    self._sse_clients.remove(handler)

    def wait_until_ready(self, *, timeout_s: float = 10.0) -> None:
        deadline = time.monotonic() + timeout_s
        last_err: OSError | None = None
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((self.host, self.port), timeout=0.5):
                    return
            except OSError as exc:
                last_err = exc
                time.sleep(0.05)
        msg = f"Live server not ready on {self.host}:{self.port}: {last_err}"
        raise TimeoutError(msg)

    def shutdown(self) -> None:
        if self._vscdb_watcher is not None:
            self._vscdb_watcher.stop()
            self._vscdb_watcher = None
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _conn(self) -> Any:
        writer = CaptureWriter(self.project_root)
        return writer, writer.connection

    def _handle_get(self, handler: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(handler.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            self._serve_asset(handler, "index.html", "text/html; charset=utf-8")
            return
        if path == "/session.html":
            self._serve_asset(handler, "session.html", "text/html; charset=utf-8")
            return
        if path.startswith("/assets/"):
            name = path[len("/assets/") :]
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            self._serve_asset(handler, name, ctype)
            return

        if _API_OVERVIEW.match(path):
            self._overview(handler, query)
            return
        if _API_CHARTS.match(path):
            self._json(handler, charts_payload, query, days=30, project=None, source=None)
            return
        if _API_SESSIONS.match(path):
            self._json(handler, sessions_payload, query, days=30, limit=50, offset=0)
            return
        match = _API_SESSION.match(path)
        if match:
            self._json(handler, session_payload, query, run_id=match.group(1))
            return
        match = _API_PROFILE.match(path)
        if match:
            self._json(handler, _profile_payload, query, run_id=match.group(1))
            return
        if _API_RECOVERABLE.match(path):
            self._json(handler, _recoverable_payload, query, days=30)
            return
        if _API_BEHAVIOR.match(path):
            self._json(handler, _behavior_payload, query, days=30, project=None)
            return
        if _API_OUTCOMES.match(path):
            self._json(handler, _outcomes_payload, query, days=30)
            return
        if _API_INSIGHTS.match(path):
            self._insights(handler, query)
            return
        if _API_OPTIMIZE.match(path):
            self._json(handler, optimize_payload, query, root=self.project_root)
            return
        if _API_SEARCH.match(path):
            self._json(handler, search_payload, query, q="", limit=20)
            return
        if _API_GAUGE.match(path):
            self._gauge(handler)
            return
        if _API_CONFIG.match(path):
            self._config_get(handler)
            return
        if _API_SETUP_SCAN.match(path):
            self._setup_scan(handler)
            return
        if _V2_EVENTS.match(path):
            self._stream_events(handler)
            return

        self._write_text(handler, HTTPStatus.NOT_FOUND, "not found", "text/plain")

    def _handle_post(self, handler: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(handler.path)
        path = parsed.path
        if _API_ACTION_OPTIMIZE.match(path):
            self._optimize_action(handler)
            return
        if _API_CONFIG.match(path):
            self._config_post(handler)
            return
        if _API_ACTION_SYNC.match(path):
            self._action_sync(handler)
            return
        if _API_ACTION_BACKFILL.match(path):
            self._action_backfill(handler)
            return
        if _API_ACTION_CHECK.match(path):
            self._action_check(handler)
            return
        if _API_ACTION_MCP.match(path):
            self._action_mcp_install(handler)
            return
        if _API_ACTION_MCP_AUTO.match(path):
            self._action_mcp_auto_install(handler)
            return
        if _API_ACTION_SHARE.match(path):
            self._action_share(handler)
            return
        if _API_REFRESH.match(path):
            self._refresh(handler)
            return
        if not _API_ACTION.match(path):
            self._write_text(handler, HTTPStatus.NOT_FOUND, "not found", "text/plain")
            return
        length = int(handler.headers.get("Content-Length", "0"))
        body = handler.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._write_text(handler, HTTPStatus.BAD_REQUEST, "invalid json", "text/plain")
            return
        result = self._run_action(str(data.get("command", "")))
        self._write_text(
            handler,
            HTTPStatus.OK,
            canonical_json(result) + "\n",
            "application/json; charset=utf-8",
        )

    def _optimize_action(self, handler: BaseHTTPRequestHandler) -> None:
        """Granular optimize actions: {apply?, revert?, measure?, rule_id?}."""
        length = int(handler.headers.get("Content-Length", "0"))
        body = handler.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._write_text(handler, HTTPStatus.BAD_REQUEST, "invalid json", "text/plain")
            return
        root = self.project_root
        apply = bool(data.get("apply"))
        revert = bool(data.get("revert"))
        measure = bool(data.get("measure"))
        rule_id = data.get("rule_id")
        days = int(data.get("days", 14))
        try:
            if revert:
                result = self._do_revert(root, rule_id)
            elif apply:
                result = self._do_apply(root, days)
            elif measure:
                from cairn.optimize.impact import run_measurement

                result = run_measurement(root)
            else:
                result = self._do_dryrun(root, days)
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "error": str(exc)}
        self._write_text(
            handler,
            HTTPStatus.OK,
            canonical_json(result) + "\n",
            "application/json; charset=utf-8",
        )

    @staticmethod
    def _do_dryrun(root: Path, days: int) -> dict[str, Any]:
        from cairn.insights.engine import evaluate
        from cairn.ledger.ledger import Ledger
        from cairn.optimize.engine import generate_proposals

        ledger = Ledger(root / ".cairn" / "ledger.db")
        try:
            insights = [i.as_dict() for i in evaluate(ledger, days=days)]
            records = generate_proposals(ledger.connection, root, days=days)
        finally:
            ledger.close()
        return {
            "ok": True,
            "action": "dryrun",
            "insights": insights,
            "proposals": [
                {
                    "kind": r.entry.kind,
                    "entry_id": r.entry.entry_id,
                    "content": r.entry.content,
                    "candidates": r.candidates,
                    "selected_index": r.selected_index,
                    "confidence": r.entry.confidence,
                    "evidence": r.evidence,
                }
                for r in records
            ],
        }

    @staticmethod
    def _do_apply(root: Path, days: int) -> dict[str, Any]:
        from cairn.ledger.ledger import Ledger
        from cairn.optimize.apply import apply_proposals
        from cairn.optimize.engine import generate_proposals
        from cairn.optimize.impact import run_measurement
        from cairn.optimize.targets import observed_sources_from_ledger

        ledger = Ledger(root / ".cairn" / "ledger.db")
        try:
            records = generate_proposals(ledger.connection, root, days=days)
            observed = observed_sources_from_ledger(root)
        finally:
            ledger.close()
        if not records:
            measurement = run_measurement(root)
            return {"ok": True, "action": "apply", "applied": 0, "measurement": measurement}
        result = apply_proposals(root, records, force=True, observed_sources=observed)
        measurement = run_measurement(root)
        return {
            "ok": not result.refused,
            "action": "apply",
            "applied": result.applied,
            "refused": result.refused,
            "diff": result.diff,
            "measurement": measurement,
        }

    @staticmethod
    def _do_revert(root: Path, rule_id: str | None) -> dict[str, Any]:
        from cairn.optimize.apply import revert_entries

        spec = str(rule_id) if rule_id else "all"
        rc = revert_entries(root, spec)
        return {"ok": True, "action": "revert", "rule_id": rule_id, "rc": rc}

    def _run_action(self, command: str) -> dict[str, Any]:
        import subprocess

        allowed = {
            "sync": ["cairn", "sync", str(self.project_root)],
            "optimize": ["cairn", "optimize", str(self.project_root)],
            "optimize-apply": ["cairn", "optimize", "--apply"],
            "check": ["cairn", "check"],
        }
        key = command.strip().lower()
        if key not in allowed:
            return {"ok": False, "error": f"unknown command: {command}"}
        try:
            proc = subprocess.run(
                allowed[key],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            return {
                "ok": proc.returncode == 0,
                "stdout": proc.stdout[-4000:],
                "stderr": proc.stderr[-2000:],
                "exit_code": proc.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout"}

    def _overview(self, handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> None:
        days = int(query.get("days", ["30"])[0])
        project = query.get("project", [None])[0]
        source = query.get("source", [None])[0]
        writer, conn = self._conn()
        try:
            payload = overview_payload(
                conn,
                days=days,
                project=project,
                source=source,
                repo_name=self.project_root.name,
            )
        finally:
            writer.close()
        self._write_text(
            handler,
            HTTPStatus.OK,
            canonical_json(payload) + "\n",
            "application/json; charset=utf-8",
        )

    def _refresh(self, handler: BaseHTTPRequestHandler) -> None:
        """Broadcast fresh metrics to all SSE clients after an external sync."""
        writer, conn = self._conn()
        try:
            overview = overview_payload(conn, days=7, repo_name=self.project_root.name)
        finally:
            writer.close()
        self._broadcast_sse("metrics-updated", overview)
        self._write_text(
            handler,
            HTTPStatus.OK,
            canonical_json({"ok": True, "event": "metrics-updated"}) + "\n",
            "application/json; charset=utf-8",
        )

    def _json(
        self,
        handler: BaseHTTPRequestHandler,
        builder: Callable[..., dict[str, Any]],
        query: dict[str, list[str]],
        **defaults: Any,
    ) -> None:
        kwargs = dict(defaults)
        if "days" in kwargs:
            kwargs["days"] = int(query.get("days", [str(kwargs["days"])])[0])
        if "limit" in kwargs:
            kwargs["limit"] = int(query.get("limit", [str(kwargs["limit"])])[0])
        if "offset" in kwargs:
            kwargs["offset"] = int(query.get("offset", [str(kwargs["offset"])])[0])
        if "project" in kwargs:
            kwargs["project"] = query.get("project", [kwargs["project"]])[0]
        if "source" in kwargs:
            kwargs["source"] = query.get("source", [kwargs["source"]])[0]
        if "q" in kwargs:
            kwargs["q"] = query.get("q", [kwargs["q"]])[0]
        if "run_id" in kwargs and "run_id" not in query:
            pass
        writer, conn = self._conn()
        try:
            payload = builder(conn, **kwargs)
        finally:
            writer.close()
        self._write_text(
            handler,
            HTTPStatus.OK,
            canonical_json(payload) + "\n",
            "application/json; charset=utf-8",
        )

    def _insights(self, handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> None:
        days = int(query.get("days", ["14"])[0])
        ledger = Ledger(self.project_root / ".cairn" / "ledger.db")
        try:
            insights = evaluate_insights(ledger, days=days)
            files = top_files_payload(ledger.connection, days=days)
            body = canonical_json(
                {
                    "insights": [i.as_dict() for i in insights],
                    "top_files": files["files"],
                }
            )
        finally:
            ledger.close()
        self._write_text(handler, HTTPStatus.OK, body + "\n", "application/json; charset=utf-8")

    def _gauge(self, handler: BaseHTTPRequestHandler) -> None:
        from cairn.context.gauge import compute_gauge

        payload = compute_gauge(self.project_root).as_dict()
        self._write_text(
            handler,
            HTTPStatus.OK,
            canonical_json(payload) + "\n",
            "application/json; charset=utf-8",
        )

    # --- config + setup + granular actions ---------------------------------

    def _config_get(self, handler: BaseHTTPRequestHandler) -> None:
        from cairn.config import load_config_dict

        data = load_config_dict()
        payload = {
            "config": data,
            "data_notes": [] if data else ["no config.toml — using defaults"],
        }
        self._write_text(
            handler,
            HTTPStatus.OK,
            canonical_json(payload) + "\n",
            "application/json; charset=utf-8",
        )

    def _config_post(self, handler: BaseHTTPRequestHandler) -> None:
        from cairn.config import save_config_dict

        body = self._read_body(handler)
        if body is None:
            return
        data = body if isinstance(body, dict) else {}
        try:
            save_config_dict({k: v for k, v in data.items() if isinstance(v, dict)})
        except ValueError as exc:
            self._write_text(
                handler,
                HTTPStatus.BAD_REQUEST,
                canonical_json({"ok": False, "error": str(exc)}) + "\n",
                "application/json; charset=utf-8",
            )
            return
        self._invalidate_cached_payloads()
        self._write_text(
            handler,
            HTTPStatus.OK,
            canonical_json({"ok": True, "config": data}) + "\n",
            "application/json; charset=utf-8",
        )

    def _invalidate_cached_payloads(self) -> None:
        """Best-effort: full recompute is heavy; touch the ledger mtime to bust caches."""
        db = self.project_root / ".cairn" / "ledger.db"
        try:
            if db.is_file():
                import os

                os.utime(db, None)
        except OSError:
            pass

    def _setup_scan(self, handler: BaseHTTPRequestHandler) -> None:
        from cairn.ingest.detect import detect_sources

        detected = detect_sources(self.project_root)
        agents = [
            {
                "source": d.source,
                "path": str(d.path) if d.path else None,
                "sessions_seen": int(d.sessions_seen),
            }
            for d in detected
        ]
        total = sum(
            a["sessions_seen"] for a in agents if isinstance(a["sessions_seen"], int)
        )
        payload = {
            "agents": agents,
            "total_sessions": total,
            "project_root": str(self.project_root),
            "data_notes": [] if agents else ["no agent history detected in this project"],
        }
        self._write_text(
            handler,
            HTTPStatus.OK,
            canonical_json(payload) + "\n",
            "application/json; charset=utf-8",
        )

    def _read_body(self, handler: BaseHTTPRequestHandler) -> Any:
        length = int(handler.headers.get("Content-Length", "0"))
        raw = handler.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            self._write_text(handler, HTTPStatus.BAD_REQUEST, "invalid json", "text/plain")
            return None

    def _action_sync(self, handler: BaseHTTPRequestHandler) -> None:
        body = self._read_body(handler)
        if body is None:
            return
        from cairn.ingest.backfill import recompute_rollups
        from cairn.ingest.ingest import run_ingest

        source = str(body.get("source", "all") or "all") if isinstance(body, dict) else "all"
        reports = run_ingest(self.project_root, source=source)
        writer = CaptureWriter(self.project_root)
        try:
            recompute_rollups(writer, days=90)
        finally:
            writer.close()
        result = {
            "ok": True,
            "action": "sync",
            "inserted": sum(r.inserted for r in reports),
            "skipped": sum(r.skipped for r in reports),
            "sources": [
                {"source": r.source, "inserted": r.inserted, "skipped": r.skipped} for r in reports
            ],
        }
        writer, conn = self._conn()
        try:
            overview = overview_payload(conn, days=7, repo_name=self.project_root.name)
        finally:
            writer.close()
        self._broadcast_sse("metrics-updated", overview)
        self._write_text(
            handler, HTTPStatus.OK, canonical_json(result) + "\n", "application/json; charset=utf-8"
        )

    def _action_backfill(self, handler: BaseHTTPRequestHandler) -> None:
        from cairn.ingest.backfill import backfill_ledger

        stats = backfill_ledger(self.project_root)
        self._write_text(
            handler,
            HTTPStatus.OK,
            canonical_json({"ok": True, "action": "backfill", "stats": stats}) + "\n",
            "application/json; charset=utf-8",
        )

    def _action_check(self, handler: BaseHTTPRequestHandler) -> None:
        import argparse as _ap
        import io
        from contextlib import redirect_stdout

        from cairn.cli.main import cmd_check

        body = self._read_body(handler) or {}
        min_q = body.get("min_quality") if isinstance(body, dict) else None
        if min_q is None:
            from cairn.config import get_setting

            cfg_val = get_setting("budgets", "min_quality")
            if cfg_val is not None:
                try:
                    min_q = float(cfg_val)
                except (TypeError, ValueError):
                    min_q = None

        ns = _ap.Namespace(
            project=self.project_root,
            budget_usd=body.get("budget_usd") if isinstance(body, dict) else None,
            budget_tokens=body.get("budget_tokens") if isinstance(body, dict) else None,
            max_waste_ratio=body.get("max_waste_ratio") if isinstance(body, dict) else None,
            min_quality=min_q,
            days=body.get("days") if isinstance(body, dict) else None,
            run=body.get("run") if isinstance(body, dict) else None,
            json=True,
            repo=None,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_check(ns)
        try:
            issues = json.loads(buf.getvalue())
        except json.JSONDecodeError:
            issues = []
        reasons = [i.get("message", str(i)) for i in issues if i.get("severity") == "error"]
        if not reasons:
            reasons = [i.get("message", str(i)) for i in issues]
        result = {"pass": rc == 0, "reasons": reasons, "issues": issues}
        self._write_text(
            handler, HTTPStatus.OK, canonical_json(result) + "\n", "application/json; charset=utf-8"
        )

    def _action_mcp_install(self, handler: BaseHTTPRequestHandler) -> None:
        body = self._read_body(handler)
        if body is None:
            return
        client = str(body.get("client", "")) if isinstance(body, dict) else ""
        from cairn.cli.main import _detect_mcp_client, _mcp_config_block, _mcp_write_config

        client = client or _detect_mcp_client()
        exe = sys.executable or "python3"
        wrote = _mcp_write_config(client, exe, self.project_root)
        block = _mcp_config_block(client, exe, self.project_root)
        result = {
            "ok": True,
            "action": "mcp_install",
            "client": client,
            "installed": wrote,
            "config_block": block,
        }
        self._write_text(
            handler, HTTPStatus.OK, canonical_json(result) + "\n", "application/json; charset=utf-8"
        )

    def _action_mcp_auto_install(self, handler: BaseHTTPRequestHandler) -> None:
        from cairn.cli.main import mcp_auto_install_clients

        installed = mcp_auto_install_clients(self.project_root)
        result = {"ok": True, "action": "mcp_auto_install", "installed": installed}
        self._write_text(
            handler, HTTPStatus.OK, canonical_json(result) + "\n", "application/json; charset=utf-8"
        )

    def _action_share(self, handler: BaseHTTPRequestHandler) -> None:
        body = self._read_body(handler)
        if body is None:
            return
        run_id = str(body.get("run_id", "")) if isinstance(body, dict) else ""
        from cairn.render.scrub import scrub_text
        from cairn.render.session_payload import session_payload

        if not run_id:
            self._write_text(
                handler,
                HTTPStatus.BAD_REQUEST,
                canonical_json({"ok": False, "error": "run_id required"}) + "\n",
                "application/json; charset=utf-8",
            )
            return
        ledger = Ledger(self.project_root / ".cairn" / "ledger.db")
        try:
            payload = session_payload(ledger.connection, run_id=run_id)
        finally:
            ledger.close()
        html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>Session {run_id}</title></head><body><pre>"
            f"{scrub_text(json.dumps(payload, indent=2, default=str))}"
            f"</pre></body></html>"
        )
        result = {"ok": True, "action": "share", "run_id": run_id, "html": html}
        self._write_text(
            handler, HTTPStatus.OK, canonical_json(result) + "\n", "application/json; charset=utf-8"
        )

    def _stream_events(self, handler: BaseHTTPRequestHandler) -> None:
        handler.close_connection = False
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "keep-alive")
        handler.end_headers()
        handler.wfile.write(b": connected\n\n")
        handler.wfile.flush()
        try:
            writer, conn = self._conn()
            try:
                overview = overview_payload(conn, days=7, repo_name=self.project_root.name)
                opt = optimize_payload(conn)
            finally:
                writer.close()
            handler.wfile.write(_sse("metrics-updated", overview))
            handler.wfile.write(_sse("optimize-proposals", opt))
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

        with self._sse_lock:
            self._sse_clients.append(handler)
        try:
            while True:
                time.sleep(25.0)
                handler.wfile.write(b": ping\n\n")
                handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with self._sse_lock:
                if handler in self._sse_clients:
                    self._sse_clients.remove(handler)

    @staticmethod
    def _serve_asset(handler: BaseHTTPRequestHandler, name: str, content_type: str) -> None:
        pkg = resources.files(_ASSETS_PKG)
        src = pkg / name
        with resources.as_file(src) as src_path:
            body = src_path.read_bytes()
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-cache")
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
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(encoded)


def _sse(event: str, data: dict[str, Any]) -> bytes:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode()


# ---------------------------------------------------------------------------
# Phase-B pillar payload builders (thin wrappers over the pillar modules)
# ---------------------------------------------------------------------------


def _profile_payload(conn: Any, *, run_id: str) -> dict[str, Any]:
    from cairn.profile.compute import profile_payload

    return profile_payload(conn, run_id=run_id)


def _recoverable_payload(conn: Any, *, days: int = 30) -> dict[str, Any]:
    from cairn.profile.compute import recoverable_payload

    return recoverable_payload(conn, days=days)


def _behavior_payload(conn: Any, *, days: int = 30, project: str | None = None) -> dict[str, Any]:
    from cairn.metrics.fingerprint import behavior_payload

    return behavior_payload(conn, days=days, project=project)


def _outcomes_payload(conn: Any, *, days: int = 30) -> dict[str, Any]:
    from cairn.outcomes import outcomes_payload

    return outcomes_payload(conn, days=days)
