"""Phase 4 hook and Codex ingest tests (R19.5, R19.8)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from cairn.ingest.hook_cmd import run_hook
from cairn.ingest.normalizer import assign_seq
from cairn.ingest.parsers.codex import parse_rollout_file
from cairn.ingest.watch import (
    _build_codex_hooks_toml,
    resolve_hook_command,
    resolve_hook_invocation,
)
from cairn.ingest.writer import CaptureWriter

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"
CODEX_FIXTURE = FIXTURES / "codex_mini.jsonl"


def test_codex_parser_golden_events() -> None:
    repo = Path("/tmp/cairn-codex-fixture")
    repo.mkdir(parents=True, exist_ok=True)
    parsed = parse_rollout_file(CODEX_FIXTURE, repo_root=repo)
    assert parsed is not None
    assert parsed.external_id == "codex-sess-redacted"
    assert parsed.model == "gpt-test"
    assert parsed.usage.usage.input_tokens == 12

    events = assign_seq(
        [{k: v for k, v in e.items() if k not in ("line_no",)} for e in parsed.events]
    )
    types = [e["type"] for e in events]
    assert "session_start" in types
    assert "user_prompt" in types
    assert "tool_call" in types
    assert "tool_result" in types
    tool_call = next(e for e in events if e["type"] == "tool_call")
    assert tool_call["name"] == "bash"
    assert tool_call["tool_use_id"] == "call_test_01"


def test_hook_malformed_stdin_exits_zero() -> None:
    assert run_hook(event="SessionStart", source="claude-code") == 0


def test_hook_file_snapshot_round_trip(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    target = repo / "src" / "app.py"
    target.parent.mkdir(parents=True)
    target.write_text("before\n", encoding="utf-8")

    writer = CaptureWriter(repo)
    try:
        run_id = writer.begin_session(
            source="claude-code",
            external_id="hook-test-session",
            cwd=str(repo),
        )
        before_hash = writer.snapshot_file_hash(str(target), None)
        assert before_hash is not None
        path_rel = "src/app.py"
        pre_seq = writer.append_event(
            run_id,
            {
                "type": "file_snapshot",
                "path_rel": path_rel,
                "op": "edit",
                "before_hash": before_hash,
            },
        )
        writer.record_file_before(run_id, path_rel, before_hash, pre_seq)

        target.write_text("after\n", encoding="utf-8")
        after_hash = writer.snapshot_file_hash(str(target), None)
        assert after_hash is not None
        assert after_hash != before_hash
        post_seq = writer.append_event(
            run_id,
            {
                "type": "file_snapshot",
                "path_rel": path_rel,
                "op": "edit",
                "after_hash": after_hash,
            },
        )
        writer.record_file_after(run_id, path_rel, after_hash, post_seq)
        writer.finish_session(run_id)

        row = writer.connection.execute(
            """
            SELECT before_hash, after_hash FROM file_artifacts
            WHERE run_id = ? AND path_rel = ?
            """,
            (run_id, path_rel),
        ).fetchone()
        assert row is not None
        assert row["before_hash"] == before_hash
        assert row["after_hash"] == after_hash
    finally:
        writer.close()


def test_hook_cli_malformed_stdin_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "cairn", "hook", "--event", "Stop", "--source", "claude-code"],
        input="not-json",
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).parent.parent,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent)},
    )
    assert result.returncode == 0


def test_hook_bash_post_tool_emits_tool_call(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    payload = {
        "session_id": "bash-hook-session",
        "cwd": str(repo),
        "tool_name": "Bash",
        "tool_use_id": "toolu_bash_01",
        "tool_input": {"command": "echo hello"},
        "tool_response": {"stdout": "hello\n", "stderr": ""},
    }
    with patch("sys.stdin", StringIO(json.dumps(payload))):
        assert run_hook(event="PostToolUse", source="claude-code") == 0

    writer = CaptureWriter(repo)
    try:
        run_id = writer.connection.execute(
            "SELECT run_id FROM runs WHERE external_id = ?",
            ("bash-hook-session",),
        ).fetchone()[0]
        types = [
            row[0]
            for row in writer.connection.execute(
                "SELECT event_type FROM events WHERE run_id = ? ORDER BY seq",
                (run_id,),
            ).fetchall()
        ]
        assert types == ["tool_call", "tool_result"]
    finally:
        writer.close()


def test_hook_edit_file_snapshots_via_stdin(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    target = repo / "README.md"
    repo.mkdir()
    target.write_text("before\n", encoding="utf-8")
    session_id = "edit-hook-session"
    cwd = str(repo)

    pre = {
        "session_id": session_id,
        "cwd": cwd,
        "tool_name": "Edit",
        "tool_use_id": "toolu_edit_01",
        "tool_input": {"file_path": str(target)},
    }
    with patch("sys.stdin", StringIO(json.dumps(pre))):
        assert run_hook(event="PreToolUse", source="claude-code") == 0

    target.write_text("after\n", encoding="utf-8")
    post = {
        "session_id": session_id,
        "cwd": cwd,
        "tool_name": "Edit",
        "tool_use_id": "toolu_edit_01",
        "tool_input": {"file_path": str(target)},
        "tool_response": {"stdout": "OK", "stderr": ""},
    }
    with patch("sys.stdin", StringIO(json.dumps(post))):
        assert run_hook(event="PostToolUse", source="claude-code") == 0

    writer = CaptureWriter(repo)
    try:
        run_id = writer.connection.execute(
            "SELECT run_id FROM runs WHERE external_id = ?",
            (session_id,),
        ).fetchone()[0]
        row = writer.connection.execute(
            """
            SELECT before_hash, after_hash FROM file_artifacts
            WHERE run_id = ? AND path_rel = 'README.md'
            """,
            (run_id,),
        ).fetchone()
        assert row is not None
        assert row["before_hash"]
        assert row["after_hash"]
        assert row["before_hash"] != row["after_hash"]
    finally:
        writer.close()


def test_hook_command_uses_absolute_path() -> None:
    invocation = resolve_hook_invocation()
    assert "/" in invocation or invocation.endswith("cairn")
    cmd = resolve_hook_command("SessionStart", "claude-code")
    assert "hook --event SessionStart --source claude-code" in cmd
    assert not cmd.startswith("cairn hook")
    assert '""' not in cmd


def test_strip_cairn_watch_preserves_hooks_state() -> None:
    from cairn.ingest.watch import CAIRN_WATCH_BEGIN, CAIRN_WATCH_END, _strip_cairn_watch_block

    content = f"""before = true
{CAIRN_WATCH_BEGIN}
[features]
hooks = true

[hooks.state]
[hooks.state."/cfg:session_start:0:0"]
trusted_hash = "sha256:abc"
{CAIRN_WATCH_END}
after = true
"""
    stripped, hooks_state = _strip_cairn_watch_block(content)
    assert CAIRN_WATCH_BEGIN not in stripped
    assert "before = true" in stripped
    assert "after = true" in stripped
    assert "[hooks.state]" in hooks_state
    assert "trusted_hash" in hooks_state


def test_codex_hook_toml_commands_are_valid() -> None:
    block = _build_codex_hooks_toml("codex")
    assert 'command = ""/' not in block
    assert 'command = "/' in block or 'command = "\\"' in block
    for line in block.splitlines():
        if line.startswith("command = "):
            value = line.removeprefix("command = ")
            assert value.startswith('"') and value.endswith('"')
            assert not value.startswith('""')


def test_codex_ingest_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_rollout_file(CODEX_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        first = writer.ingest_codex_session(parsed)
        second = writer.ingest_codex_session(parsed)
        assert first.inserted is True
        assert second.inserted is False
        count = writer.connection.execute(
            "SELECT COUNT(*) FROM runs WHERE source = 'codex' AND external_id = ?",
            (parsed.external_id,),
        ).fetchone()[0]
        assert count == 1
    finally:
        writer.close()
