"""Phase 13 live workspace server tests."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from cairn.live.server import LiveServer
from tests.test_capture_phase5 import CLAUDE_FIXTURE


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def test_live_server_session_routes(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        writer.ingest_claude_session(parsed)
    finally:
        writer.close()

    port = _free_port()
    server = LiveServer(repo, port=port)
    server.serve_background()
    try:
        base = server.base_url
        status, html = _get(f"{base}/session/{parsed.external_id}")
        assert status == 200
        assert "live_events_url" in html
        assert "capture.js" in html

        status, body = _get(f"{base}/session/{parsed.external_id}/data.json")
        assert status == 200
        payload = json.loads(body)
        assert payload["cairn_bundle_version"] == 3
        assert payload["session"]["external_id"] == parsed.external_id

        status, _css = _get(f"{base}/assets/app.css")
        assert status == 200
    finally:
        server.shutdown()


def test_live_server_sse_finish(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        writer.ingest_claude_session(parsed)
    finally:
        writer.close()

    port = _free_port()
    server = LiveServer(repo, port=port)
    server.serve_background()
    try:
        with urllib.request.urlopen(
            f"{server.base_url}/session/{parsed.external_id}/events",
            timeout=5,
        ) as resp:
            chunks = resp.read(4096).decode("utf-8")
        assert "event: append" in chunks
        assert "event: finish" in chunks
        assert parsed.external_id in chunks
    finally:
        server.shutdown()
