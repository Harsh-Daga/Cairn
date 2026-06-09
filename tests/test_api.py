"""Phase 17 HTTP API tests."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

from cairn.api.openapi import openapi_spec
from cairn.api.server import ApiServer
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from tests.test_capture_phase5 import CLAUDE_FIXTURE


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _get_json(url: str) -> tuple[int, dict[str, object]]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_openapi_spec_has_paths() -> None:
    spec = openapi_spec()
    assert spec["openapi"] == "3.0.3"
    assert "/v1/sessions/{session_id}" in spec["paths"]


def test_api_sessions_and_report(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        result = writer.ingest_claude_session(parsed)
        run_id = result.run_id
    finally:
        writer.close()

    port = _free_port()
    server = ApiServer(repo, port=port)
    server.serve_background()
    try:
        base = server.base_url
        status, spec = _get_json(f"{base}/v1/openapi.json")
        assert status == 200
        assert "paths" in spec

        status, sessions_payload = _get_json(f"{base}/v1/projects/{repo.name}/sessions")
        assert status == 200
        sessions = sessions_payload["sessions"]
        assert isinstance(sessions, list)
        assert len(sessions) == 1

        session_id = parsed.external_id
        status, session_payload = _get_json(f"{base}/v1/sessions/{session_id}")
        assert status == 200
        assert session_payload["session_id"] == session_id

        status, report_payload = _get_json(f"{base}/v1/runs/{run_id}/report")
        assert status == 200
        assert report_payload["kind"] == "capture"

        with urllib.request.urlopen(f"{base}/v1/sessions/{session_id}/events", timeout=5) as resp:
            chunks = resp.read(4096).decode("utf-8")
        assert "event: finish" in chunks
    finally:
        server.shutdown()


def test_api_workflow_dry_run(project_dir: Path) -> None:
    port = _free_port()
    server = ApiServer(project_dir, port=port)
    server.serve_background()
    try:
        url = f"{server.base_url}/v1/workflows/default/run"
        request = urllib.request.Request(
            url,
            data=json.dumps({"dry_run": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        assert payload.get("dry_run") is True
        assert payload.get("ok") is True
    finally:
        server.shutdown()
