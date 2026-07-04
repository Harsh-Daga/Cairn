"""Live workspace server tests."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from cairn.live.server import LiveServer
from tests.test_cursor_capture import CLAUDE_FIXTURE


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


def test_live_server_routes(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        result = writer.ingest_claude_session(parsed)
    finally:
        writer.close()

    port = _free_port()
    server = LiveServer(repo, port=port)
    server.serve_background()
    try:
        base = server.base_url

        status, html = _get(f"{base}/")
        assert status == 200
        assert "dashboard.js" in html
        # Phase E: design-system CDN + font references present (Part 18.3)
        assert "chart.js@4.4" in html
        assert "chartjs-adapter-date-fns" in html
        assert "d3@7" in html
        assert "dompurify" in html
        assert "Fraunces" in html
        assert "Space+Grotesk" in html
        assert "JetBrains+Mono" in html
        # 10 pages present
        for page in (
            "page-overview",
            "page-context",
            "page-behavior",
            "page-quality",
            "page-charts",
            "page-insights",
            "page-optimize",
            "page-sessions",
            "page-search",
            "page-settings",
        ):
            assert page in html, f"missing {page}"

        status, html = _get(f"{base}/session.html?id={result.run_id}")
        assert status == 200
        assert "session.js" in html
        assert "d3@7" in html
        assert "dompurify" in html

        status, body = _get(f"{base}/api/session/{result.run_id}")
        assert status == 200
        payload = json.loads(body)
        assert payload["run"]["run_id"] == result.run_id
        assert "turns" in payload
        assert "graph" in payload
        assert "fingerprint" in payload  # Phase E render-payload addition

        status, body = _get(f"{base}/api/overview?days=30")
        assert status == 200
        overview = json.loads(body)
        assert "summary" in overview

        # Phase E: all assets serve 200
        for asset in ("dashboard.css", "dashboard.js", "session.css", "session.js"):
            status, _ = _get(f"{base}/assets/{asset}")
            assert status == 200, asset
    finally:
        server.shutdown()


def test_live_server_refresh_broadcasts_sse(tmp_path: Path) -> None:
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
        req = urllib.request.Request(
            f"{server.base_url}/api/refresh",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
        assert body["ok"] is True
        assert body["event"] == "metrics-updated"
    finally:
        server.shutdown()


def test_live_server_sse_v2_events(tmp_path: Path) -> None:
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
            f"{server.base_url}/v2/events",
            timeout=5,
        ) as resp:
            text = ""
            for _ in range(30):
                line = resp.readline().decode("utf-8")
                if not line:
                    break
                text += line
                if "optimize-proposals" in text:
                    break
        assert "event: metrics-updated" in text
        assert "event: optimize-proposals" in text
    finally:
        server.shutdown()
