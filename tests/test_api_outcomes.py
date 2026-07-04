"""GET /api/outcomes — quality + cost_per_success + funnel, nulls + data_notes."""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from cairn.ingest.parsers.claude_code import ToolCallDraft
from cairn.ingest.usage import UsageAccumulator
from cairn.ingest.writer import CaptureWriter
from cairn.live.server import LiveServer


def _git_repo() -> Path:
    d = Path(tempfile.mkdtemp())
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    (d / "a.py").write_text("print(1)\n")
    subprocess.run(["git", "add", "."], cwd=d, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=d, check=True)
    return d


def _ingest(tmp_path: Path, events, tool_calls, *, cwd=None, external_id="s1"):
    w = CaptureWriter(tmp_path)
    res = w._ingest_session(
        source="claude-code",
        external_id=external_id,
        cwd=cwd or str(tmp_path),
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


def _clean_session(ext):
    events = [
        {"type": "user_prompt", "text": "q", "text_hash": f"h-{ext}"},
        {
            "type": "tool_call",
            "tool_use_id": "r1",
            "name": "read",
            "args_inline": {"file_path": "a.py"},
            "args_hash": "rh1",
        },
        {"type": "tool_result", "tool_use_id": "r1", "result_inline": "x", "result_hash": "rr1"},
        {
            "type": "tool_call",
            "tool_use_id": "e1",
            "name": "edit",
            "args_inline": {"file_path": "a.py"},
            "args_hash": "eh1",
        },
        {"type": "tool_result", "tool_use_id": "e1", "result_inline": "ok", "result_hash": "er1"},
        {
            "type": "tool_call",
            "tool_use_id": "r2",
            "name": "read",
            "args_inline": {"file_path": "a.py"},
            "args_hash": "rh2",
        },
        {"type": "tool_result", "tool_use_id": "r2", "result_inline": "y", "result_hash": "rr2"},
        {
            "type": "assistant_message",
            "text": "a",
            "model": "claude-sonnet-4-5",
            "input_tokens": 500,
            "output_tokens": 100,
            "usage": {"input_tokens": 500, "output_tokens": 100},
        },
    ]
    tools = [
        ToolCallDraft("r1", "read", "rh1", 2, "a.py"),
        ToolCallDraft("e1", "edit", "eh1", 4, "a.py"),
        ToolCallDraft("r2", "read", "rh2", 6, "a.py"),
    ]
    return events, tools


def test_api_outcomes_shape(tmp_path: Path) -> None:
    repo = _git_repo()
    # Use the ledger at tmp_path but point the session cwd at the git repo so
    # outcome git capture finds commits.
    ev, tc = _clean_session("s1")
    run_id = _ingest(tmp_path, ev, tc, cwd=str(repo), external_id="s1")
    # Land a commit in the repo after the session started.
    (repo / "b.py").write_text("x = 2\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "feat: b"], cwd=repo, check=True)
    # Recompute outcomes so git signals pick up the commit.
    from cairn.ingest.backfill import backfill_run
    from cairn.ingest.writer import CaptureWriter as CW

    w = CW(tmp_path)
    backfill_run(w, run_id)
    w.close()

    server = LiveServer(tmp_path, port=18796)
    server.serve_background()
    try:
        with urlopen(f"{server.base_url}/api/outcomes?days=30") as resp:
            data = json.loads(resp.read())
        assert data["quality"] is not None
        assert "tier_counts" in data["quality"]
        assert data["cost_per_success"] is not None
        assert data["funnel"] is not None
        assert data["funnel"]["sessions"] >= 1
        assert isinstance(data["sessions"], list)
        assert "data_notes" in data
    finally:
        server.shutdown()


def test_api_outcomes_empty_state(tmp_path: Path) -> None:
    server = LiveServer(tmp_path, port=18797)
    server.serve_background()
    try:
        with urlopen(f"{server.base_url}/api/outcomes?days=30") as resp:
            data = json.loads(resp.read())
        assert data["quality"] is None
        assert data["cost_per_success"] is None
        assert data["funnel"] is None
        assert data["sessions"] is None
        # data_notes explain how to enable tests.
        assert any("test_command" in n for n in data["data_notes"])
    finally:
        server.shutdown()
