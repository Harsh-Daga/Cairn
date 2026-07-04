"""Phase 2 — Stop hook and post-session autopsy tests."""

from __future__ import annotations

import ast
import inspect
import io
import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from cairn.cli.guard import run_post_session, run_stop_hook
from cairn.ingest.usage import UsageAccumulator
from cairn.ingest.writer import CaptureWriter


def _healthy_events() -> list[dict]:
    return [
        {"type": "user_prompt", "text": "hi", "text_hash": "h1"},
        {"type": "assistant_message", "text": "hello", "input_tokens": 10, "output_tokens": 5},
    ]


def test_stop_hook_silent_and_fast(tmp_path: Path, capsys) -> None:
    payload = json.dumps({"session_id": "s1", "cwd": str(tmp_path)})
    start = time.monotonic()
    with (
        patch("sys.stdin", io.StringIO(payload)),
        patch("cairn.cli.guard.subprocess.Popen") as popen,
    ):
        popen.return_value = None
        rc = run_stop_hook()
    elapsed_ms = (time.monotonic() - start) * 1000
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip() == ""
    assert elapsed_ms < 200
    popen.assert_called_once()


def test_stop_hook_never_blocks() -> None:
    src = inspect.getsource(run_stop_hook)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
        ):
            raise AssertionError("run_stop_hook must not print")


def test_post_session_computes_diagnostics(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    writer = CaptureWriter(root)
    try:
        res = writer._ingest_session(
            source="claude-code",
            external_id="post-sess",
            cwd=str(root),
            git_branch=None,
            started_at=datetime.now(UTC).isoformat(),
            ended_at=None,
            model="claude-sonnet-4-5",
            events=_healthy_events(),
            tool_calls=[],
            usage=UsageAccumulator().usage,
        )
        run_id = res.run_id
    finally:
        writer.close()

    conn = sqlite3.connect(root / ".cairn" / "ledger.db")
    conn.row_factory = sqlite3.Row
    conn.execute("DELETE FROM diagnostics WHERE run_id = ?", (run_id,))
    conn.commit()
    row_before = conn.execute(
        "SELECT run_id FROM diagnostics WHERE run_id = ?", (run_id,)
    ).fetchone()
    conn.close()
    assert row_before is None

    with patch("cairn.ingest.ingest.run_ingest", return_value=[]):
        rc = run_post_session(session_id="post-sess", cwd=str(root))
    assert rc == 0

    conn = sqlite3.connect(root / ".cairn" / "ledger.db")
    conn.row_factory = sqlite3.Row
    row_after = conn.execute(
        "SELECT run_id FROM diagnostics WHERE run_id = ?", (run_id,)
    ).fetchone()
    conn.close()
    assert row_after is not None
