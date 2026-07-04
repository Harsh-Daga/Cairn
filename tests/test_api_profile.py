"""GET /api/profile/{run_id} and /api/recoverable — shape, nulls, data_notes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from cairn.ingest.parsers.claude_code import ToolCallDraft
from cairn.ingest.usage import UsageAccumulator
from cairn.ingest.writer import CaptureWriter
from cairn.live.server import LiveServer


def _ingest(tmp_path: Path, events, tool_calls, external_id="s1"):
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


def _session_events():
    return [
        {"type": "user_prompt", "text": "q1", "text_hash": "h1"},
        {
            "type": "tool_call",
            "tool_use_id": "t1",
            "name": "read",
            "args_inline": {"file_path": "a.py"},
            "args_hash": "ah1",
        },
        {
            "type": "tool_result",
            "tool_use_id": "t1",
            "result_inline": "x" * 4000,
            "result_hash": "rh1",
        },
        {
            "type": "assistant_message",
            "text": "a1",
            "model": "claude-sonnet-4-5",
            "input_tokens": 1200,
            "output_tokens": 50,
            "usage": {"input_tokens": 1200, "output_tokens": 50},
        },
        {"type": "user_prompt", "text": "q2", "text_hash": "h2"},
        {
            "type": "assistant_message",
            "text": "a2",
            "model": "claude-sonnet-4-5",
            "input_tokens": 1300,
            "output_tokens": 40,
            "usage": {"input_tokens": 1300, "output_tokens": 40},
        },
        {"type": "user_prompt", "text": "q3", "text_hash": "h3"},
        {
            "type": "assistant_message",
            "text": "a3",
            "model": "claude-sonnet-4-5",
            "input_tokens": 1400,
            "output_tokens": 30,
            "usage": {"input_tokens": 1400, "output_tokens": 30},
        },
    ]


def test_api_profile_shape(tmp_path: Path) -> None:
    run_id = _ingest(tmp_path, _session_events(), [ToolCallDraft("t1", "read", "ah1", 2, "a.py")])
    server = LiveServer(tmp_path, port=18791)
    server.serve_background()
    try:
        with urlopen(f"{server.base_url}/api/profile/{run_id}") as resp:
            data = json.loads(resp.read())
        assert data["run_id"] == run_id
        assert isinstance(data["regions"], list) and data["regions"]
        assert isinstance(data["findings"], list)
        assert "rebilling" in data and data["rebilling"] is not None
        assert isinstance(data["data_notes"], list)
        # region rows have the expected fields.
        r0 = data["regions"][0]
        assert {"event_id", "region", "tokens", "cost", "content_hash"} <= set(r0)
    finally:
        server.shutdown()


def test_api_profile_empty_state_nulls(tmp_path: Path) -> None:
    # A run with no assistant turns → no regions → nulls not zeros.
    events = [{"type": "user_prompt", "text": "q", "text_hash": "h"}]
    run_id = _ingest(tmp_path, events, [], external_id="s2")
    server = LiveServer(tmp_path, port=18792)
    server.serve_background()
    try:
        with urlopen(f"{server.base_url}/api/profile/{run_id}") as resp:
            data = json.loads(resp.read())
        assert data["regions"] is None
        assert data["findings"] is None
        assert data["rebilling"] is None
        assert data["data_notes"]
    finally:
        server.shutdown()


def test_api_recoverable_shape(tmp_path: Path) -> None:
    _ingest(tmp_path, _session_events(), [ToolCallDraft("t1", "read", "ah1", 2, "a.py")])
    server = LiveServer(tmp_path, port=18793)
    server.serve_background()
    try:
        with urlopen(f"{server.base_url}/api/recoverable?days=30") as resp:
            data = json.loads(resp.read())
        assert "data_notes" in data
        # Either weeks list (has data) or null (empty) — both valid shapes.
        if data["weeks"] is not None:
            assert isinstance(data["weeks"], list)
    finally:
        server.shutdown()
