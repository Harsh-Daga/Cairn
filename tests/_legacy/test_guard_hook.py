"""Phase 1 — PreToolUse guard hook contract tests."""

from __future__ import annotations

import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from cairn.cli.guard import (
    guard_install,
    handle_pretooluse,
    install_codex_hooks,
    resolve_guard_run,
    run_pretooluse_hook,
)
from cairn.config import save_config_dict
from cairn.ingest.parsers.claude_code import ToolCallDraft
from cairn.ingest.usage import UsageAccumulator
from cairn.ingest.writer import CaptureWriter
from cairn.ledger.schema import migrate


def _loop_events(n: int = 4) -> list[dict]:
    events: list[dict] = [{"type": "user_prompt", "text": "grep again", "text_hash": "h0"}]
    for i in range(n):
        uid = f"t{i}"
        events.extend(
            [
                {
                    "type": "tool_call",
                    "tool_use_id": uid,
                    "tool_name": "grep",
                    "tool_norm_name": "search",
                    "name": "grep",
                    "args_hash": "same",
                },
                {
                    "type": "tool_result",
                    "tool_use_id": uid,
                    "result_inline": "same output",
                    "result_hash": "r",
                },
            ]
        )
    events.append(
        {
            "type": "assistant_message",
            "text": "still trying",
            "input_tokens": 50,
            "output_tokens": 10,
        }
    )
    return events


def _loop_tool_calls(n: int = 4) -> list[ToolCallDraft]:
    return [ToolCallDraft(f"t{i}", "grep", "same", 2 + i * 2, None) for i in range(n)]


def _seed_loop_run(tmp_path: Path, *, external_id: str = "sess-loop") -> tuple[Path, str]:
    root = tmp_path / "proj"
    root.mkdir()
    writer = CaptureWriter(root)
    try:
        res = writer._ingest_session(
            source="claude-code",
            external_id=external_id,
            cwd=str(root),
            git_branch=None,
            started_at=datetime.now(UTC).isoformat(),
            ended_at=None,
            model="claude-sonnet-4-5",
            events=_loop_events(4),
            tool_calls=_loop_tool_calls(4),
            usage=UsageAccumulator().usage,
        )
    finally:
        writer.close()
    return root, res.run_id


def _stdin_payload(root: Path, session_id: str = "sess-loop") -> str:
    return json.dumps(
        {
            "session_id": session_id,
            "cwd": str(root),
            "hook_event_name": "PreToolUse",
            "tool_name": "grep",
        }
    )


def test_advisory_silent_when_healthy(tmp_path: Path, capsys) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    events = [
        {"type": "user_prompt", "text": "read a.py", "text_hash": "h1"},
        {
            "type": "tool_call",
            "tool_use_id": "t1",
            "tool_name": "read",
            "tool_norm_name": "read",
            "args_hash": "a1",
        },
        {"type": "tool_result", "tool_use_id": "t1", "result_inline": "ok", "result_hash": "r1"},
        {"type": "assistant_message", "text": "done", "input_tokens": 40, "output_tokens": 10},
    ]
    writer = CaptureWriter(root)
    try:
        writer._ingest_session(
            source="claude-code",
            external_id="healthy",
            cwd=str(root),
            git_branch=None,
            started_at=datetime.now(UTC).isoformat(),
            ended_at=None,
            model="claude-sonnet-4-5",
            events=events,
            tool_calls=[ToolCallDraft("t1", "read", "a1", 2, "a.py")],
            usage=UsageAccumulator().usage,
        )
    finally:
        writer.close()

    with patch("sys.stdin", io.StringIO(_stdin_payload(root, "healthy"))):
        rc = run_pretooluse_hook(mode="advisory")
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip() == ""


def test_advisory_system_message_shape(tmp_path: Path) -> None:
    root, _run_id = _seed_loop_run(tmp_path)
    result = handle_pretooluse(_stdin_payload(root), mode="advisory")
    assert result is not None
    assert set(result.keys()) == {"continue", "systemMessage"}
    assert result["continue"] is True
    assert str(result["systemMessage"]).startswith("cairn guard:")


def test_block_deny_shape(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    save_config_dict({"guard": {"allow_block": True}})
    root, _run_id = _seed_loop_run(tmp_path)
    result = handle_pretooluse(_stdin_payload(root), mode="block")
    assert result is not None
    assert "hookSpecificOutput" in result
    hso = result["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    reason = hso["permissionDecisionReason"]
    assert re.search(r"\d", reason)
    assert "Next step" in reason or "Try a different tool or target." in reason


def test_block_degrades_without_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    save_config_dict({"guard": {"allow_block": False}})
    root, _run_id = _seed_loop_run(tmp_path)
    result = handle_pretooluse(_stdin_payload(root), mode="block")
    assert result is not None
    assert set(result.keys()) == {"continue", "systemMessage"}
    assert result["continue"] is True
    assert result["systemMessage"].endswith("(block requested but guard.allow_block=false)")


def test_fail_open_malformed_stdin(capsys) -> None:
    with patch("sys.stdin", io.StringIO("not-json")):
        rc = run_pretooluse_hook(mode="advisory")
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""


def test_fail_open_no_session(tmp_path: Path, capsys) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    with patch("sys.stdin", io.StringIO(json.dumps({"cwd": str(root), "session_id": "missing"}))):
        rc = run_pretooluse_hook(mode="advisory")
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""


def test_codex_install_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    target = root / ".codex" / "hooks.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"other": true, "hooks": {}}\n', encoding="utf-8")
    install_codex_hooks(target)
    install_codex_hooks(target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["other"] is True
    pretool = data["hooks"]["PreToolUse"]
    cairn_cmds = [
        h["command"]
        for entry in pretool
        for h in entry.get("hooks", [])
        if "cairn" in str(h.get("command", ""))
    ]
    assert len(cairn_cmds) == 1


def test_resolve_guard_run_prefers_session_id(tmp_path: Path) -> None:
    import sqlite3

    root = tmp_path / "proj"
    root.mkdir()
    db = root / ".cairn" / "ledger.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    conn.execute(
        "INSERT INTO runs (run_id, source, external_id, cwd, started_at, status) "
        "VALUES ('r-old', 'claude-code', 'sess-old', ?, datetime('now', '-1 day'), 'completed')",
        (str(root),),
    )
    conn.execute(
        "INSERT INTO runs (run_id, source, external_id, cwd, started_at, status) "
        "VALUES ('r-new', 'claude-code', 'sess-new', ?, datetime('now'), 'completed')",
        (str(root),),
    )
    conn.commit()
    assert resolve_guard_run(conn, "sess-new", str(root)) == "r-new"
    conn.close()


def test_install_includes_stop_hook(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    guard_install(root, agent="claude", write=True)
    settings = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "PreToolUse" in settings["hooks"]
    assert "Stop" in settings["hooks"]
    guard_install(root, agent="claude", write=True)
    settings2 = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    stop_cmds = [
        h["command"] for entry in settings2["hooks"]["Stop"] for h in entry.get("hooks", [])
    ]
    assert len(stop_cmds) == 1
