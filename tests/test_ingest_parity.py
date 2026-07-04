"""Cross-agent ingest parity — same logical session, same normalized shape (Phase 0)."""

from __future__ import annotations

from pathlib import Path

from cairn.ingest.parsers.agent_jsonl import parse_agent_jsonl
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.parsers.cline_family import parse_cline_task
from cairn.ingest.parsers.codex import parse_rollout_file
from cairn.ingest.parsers.cursor import parse_transcript_file
from cairn.ingest.parsers.gemini_cli import parse_gemini_file
from cairn.ingest.parsers.openclaw import parse_openclaw_file
from cairn.ingest.writer import CaptureWriter, _flatten_event

_FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


def _canonical_shape(source: str, fixture: Path, tmp_path: Path) -> list[dict]:
    root = tmp_path / "proj"
    root.mkdir(exist_ok=True)
    if source == "claude-code":
        parsed = parse_jsonl_file(fixture, repo_root=root)
    elif source == "codex":
        parsed = parse_rollout_file(fixture, repo_root=root)
    elif source == "cursor":
        parsed = parse_transcript_file(fixture, repo_root=root)
    elif source in ("aider", "goose", "opencode"):
        parsed = parse_agent_jsonl(fixture, source=source, repo_root=root)  # type: ignore[arg-type]
    elif source == "gemini":
        parsed = parse_gemini_file(fixture, repo_root=root)
    elif source == "cline":
        parsed = parse_cline_task(fixture, source="cline", repo_root=root)
    elif source == "openclaw":
        parsed = parse_openclaw_file(fixture, repo_root=root)
    else:
        raise ValueError(source)
    assert parsed is not None
    from cairn.ingest.normalizer import assign_seq

    tool_by_id = {tc.tool_use_id: tc for tc in parsed.tool_calls}
    rows = [
        _flatten_event(e, source=source, tool_by_id=tool_by_id, cwd=parsed.cwd, root=root)
        for e in assign_seq(parsed.events)
    ]
    return [
        {
            "type": r["type"],
            "tool_norm_name": r.get("tool_norm_name"),
            "role": r.get("role"),
        }
        for r in rows
        if r["type"] in ("user_prompt", "assistant_message", "tool_call", "tool_result")
    ]


def test_claude_codex_cursor_share_edit_tool_norm(tmp_path: Path) -> None:
    """Mini fixtures: file-edit tools normalize to ``edit`` across agents."""
    cases: list[tuple[str, Path]] = [
        ("claude-code", _FIXTURES / "claude_code_mini.jsonl"),
        ("codex", _FIXTURES / "codex_mini.jsonl"),
        ("cursor", _FIXTURES / "cursor_mini.jsonl"),
    ]
    edit_norms: set[str | None] = set()
    for source, path in cases:
        shape = _canonical_shape(source, path, tmp_path)
        edit_calls = [
            r for r in shape if r["type"] == "tool_call" and r.get("tool_norm_name") == "edit"
        ]
        if edit_calls:
            edit_norms.add("edit")
    assert edit_norms == {"edit"}


def test_agent_jsonl_parity_with_claude_shape(tmp_path: Path) -> None:
    """Generic JSONL (aider/goose/opencode) matches claude event-type ordering."""
    claude = _canonical_shape("claude-code", _FIXTURES / "claude_code_mini.jsonl", tmp_path)
    agent = _canonical_shape("aider", _FIXTURES / "agent_jsonl_mini.jsonl", tmp_path)
    claude_types = [r["type"] for r in claude]
    agent_types = [r["type"] for r in agent]
    assert claude_types[:2] == agent_types[:2]  # user_prompt, assistant_message
    assert agent[-1]["type"] == "tool_result" or agent[-1]["type"] == "tool_call"


def test_new_parser_parity_shapes(tmp_path: Path) -> None:
    cases: list[tuple[str, Path]] = [
        ("gemini", _FIXTURES / "gemini_mini.jsonl"),
        ("cline", _FIXTURES / "cline_mini" / "tasks" / "task-redacted-001" / "ui_messages.json"),
        ("openclaw", _FIXTURES / "openclaw_mini.jsonl"),
    ]
    for source, path in cases:
        shape = _canonical_shape(source, path, tmp_path)
        types = [r["type"] for r in shape]
        assert "user_prompt" in types
        assert "tool_call" in types
        assert "tool_result" in types


def test_ingest_populates_data_quality(tmp_path: Path) -> None:
    fixture = _FIXTURES / "claude_code_mini.jsonl"
    root = tmp_path / "proj"
    root.mkdir(exist_ok=True)
    parsed = parse_jsonl_file(fixture, repo_root=root)
    assert parsed is not None
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_claude_session(parsed)
        row = writer.connection.execute(
            "SELECT pct_tokens_measured, cost_source, parser_version "
            "FROM data_quality WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
        assert row is not None
        assert row["parser_version"] is not None
        assert float(row["pct_tokens_measured"]) >= 95.0
    finally:
        writer.close()
