"""GET /api/behavior — fingerprints + drift + radar, nulls + data_notes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from cairn.ingest.parsers.claude_code import ToolCallDraft
from cairn.ingest.usage import UsageAccumulator
from cairn.ingest.writer import CaptureWriter
from cairn.live.server import LiveServer


def _ingest(tmp_path: Path, events, tool_calls, external_id):
    w = CaptureWriter(tmp_path)
    res = w._ingest_session(
        source="claude-code",
        external_id=external_id,
        cwd=str(tmp_path),
        git_branch=None,
        started_at=datetime.now(UTC).isoformat(),
        ended_at=None,
        model="claude-sonnet-4-5",
        events=events,
        tool_calls=tool_calls,
        usage=UsageAccumulator().usage,
    )
    w.close()
    return res.run_id


def _session(reads, edits, *, ext):
    events: list[dict] = []
    events.append({"type": "user_prompt", "text": "q", "text_hash": f"h-{ext}"})
    for _ in range(reads):
        events.append(
            {
                "type": "tool_call",
                "tool_use_id": f"r-{ext}",
                "name": "read",
                "args_inline": {"file_path": "a.py"},
                "args_hash": f"rh-{ext}",
            }
        )
        events.append(
            {
                "type": "tool_result",
                "tool_use_id": f"r-{ext}",
                "result_inline": "x",
                "result_hash": f"rr-{ext}",
            }
        )
    for _ in range(edits):
        events.append(
            {
                "type": "tool_call",
                "tool_use_id": f"e-{ext}",
                "name": "edit",
                "args_inline": {"file_path": "a.py"},
                "args_hash": f"eh-{ext}",
            }
        )
        events.append(
            {
                "type": "tool_result",
                "tool_use_id": f"e-{ext}",
                "result_inline": "ok",
                "result_hash": f"er-{ext}",
            }
        )
    events.append(
        {
            "type": "assistant_message",
            "text": "a",
            "model": "claude-sonnet-4-5",
            "input_tokens": 500,
            "output_tokens": 100,
            "usage": {"input_tokens": 500, "output_tokens": 100},
            "context_tokens_after": 40000,
        }
    )
    tools = [ToolCallDraft(f"r-{ext}", "read", f"rh-{ext}", 1, "a.py") for _ in range(reads)]
    tools += [ToolCallDraft(f"e-{ext}", "edit", f"eh-{ext}", 1, "a.py") for _ in range(edits)]
    return events, tools


def test_api_behavior_shape(tmp_path: Path) -> None:
    for i in range(6):
        ev, tc = _session(3, 2, ext=f"s{i}")
        _ingest(tmp_path, ev, tc, external_id=f"s{i}")
    server = LiveServer(tmp_path, port=18794)
    server.serve_background()
    try:
        with urlopen(f"{server.base_url}/api/behavior?days=30") as resp:
            data = json.loads(resp.read())
        assert data["fingerprints"] is not None
        assert isinstance(data["fingerprints"], list) and len(data["fingerprints"]) == 6
        fp0 = data["fingerprints"][0]
        assert "read_write_ratio" in fp0
        assert "run_id" in fp0
        assert "data_notes" in data
        assert data["radar"] is not None
        assert "labels" in data["radar"]
        assert "current_week" in data["radar"]
    finally:
        server.shutdown()


def test_api_behavior_empty_nulls(tmp_path: Path) -> None:
    server = LiveServer(tmp_path, port=18795)
    server.serve_background()
    try:
        with urlopen(f"{server.base_url}/api/behavior?days=30") as resp:
            data = json.loads(resp.read())
        assert data["fingerprints"] is None
        assert data["radar"] is None
        assert data["data_notes"]
    finally:
        server.shutdown()
