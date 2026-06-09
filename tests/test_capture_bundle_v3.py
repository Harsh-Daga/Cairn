"""Phase 5.5 capture bundle v3 tests (§11.8, R19.12)."""

from __future__ import annotations

from pathlib import Path

from cairn.graph.session_graph import build_session_graph
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from cairn.render.capture_bundle import capture_bundle_from_project
from cairn.render.extract import parse_cairn_data
from cairn.render.graph_layout import build_display_graph, layout_session_graph
from cairn.render.html import render_capture_bundle
from cairn.render.scrub import scrub_text
from cairn.render.turns import build_turns
from tests.test_capture_phase5 import CLAUDE_FIXTURE
from tests.test_render_embedding import _assert_no_external_resources


def test_build_turns_skips_terminal_noise() -> None:
    events = [
        {"seq": 1, "type": "user_prompt", "text_inline": "real task"},
        {"seq": 2, "type": "tool_call", "name": "bash"},
        {
            "seq": 3,
            "type": "user_prompt",
            "text_inline": "user@host proj % pip install\nlots of output",
        },
        {"seq": 4, "type": "tool_call", "name": "read"},
        {"seq": 5, "type": "user_prompt", "text_inline": "next real task"},
    ]
    turns = build_turns(events)
    assert len(turns) == 2
    assert turns[0]["user_text"] == "real task"
    assert turns[1]["user_text"] == "next real task"


def test_build_turns_groups_user_and_tools() -> None:
    events = [
        {"seq": 1, "type": "user_prompt", "text_inline": "hello"},
        {"seq": 2, "type": "assistant_message", "text_inline": "hi there"},
        {"seq": 3, "type": "tool_call", "name": "read", "args_inline": {"path": "a.py"}},
        {"seq": 4, "type": "tool_result", "tool_use_id": "t1", "result_inline": "ok"},
        {"seq": 5, "type": "user_prompt", "text_inline": "next"},
    ]
    turns = build_turns(events)
    assert len(turns) == 2
    assert turns[0]["turn_id"] == 1
    assert turns[0]["user_text"] == "hello"
    assert turns[0]["tool_count"] == 1
    assert turns[1]["user_text"] == "next"


def test_graph_layout_assigns_positions() -> None:
    events = [
        {"seq": 1, "type": "user_prompt", "text_inline": "a"},
        {"seq": 2, "type": "tool_call", "name": "read"},
    ]
    laid_out = layout_session_graph(build_session_graph(events))
    assert laid_out["layout"] == "layered-dag"
    assert laid_out["width"] > 0
    for node in laid_out["nodes"]:
        assert "x" in node
        assert "y" in node


def test_scrub_redacts_api_key_pattern() -> None:
    raw = "key=sk-abcdefghijklmnopqrstuvwxyz1234567890"
    assert "[REDACTED]" in scrub_text(raw)
    assert "sk-abc" not in scrub_text(raw)


def test_display_graph_collapses_large_sessions() -> None:
    events = [
        {"seq": i, "type": "tool_call" if i % 2 == 0 else "tool_result", "name": "read"}
        for i in range(1, 60)
    ]
    events.insert(0, {"seq": 0, "type": "user_prompt", "text_inline": "start"})
    turns = build_turns(events)
    event_graph = layout_session_graph(build_session_graph(events))
    display = build_display_graph(events, turns, event_graph)
    assert display["mode"] == "turns"
    assert len(display["nodes"]) == len(turns)
    assert display["height"] < 800


def test_capture_bundle_v3_payload(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        writer.ingest_claude_session(parsed)
    finally:
        writer.close()

    payload = capture_bundle_from_project(repo, parsed.external_id)
    assert payload["cairn_bundle_version"] == 3
    session = payload["session"]
    assert session["external_id"] == parsed.external_id
    assert session["session_key"] == f"claude-code:{parsed.external_id}"
    assert session["run_id"]
    assert len(payload["turns"]) >= 1
    if payload["files"]:
        assert payload["files"][0]["snapshot_quality"] in ("exact", "inferred", "partial")
    node = payload["graph"]["nodes"][0]
    assert "x" in node and "y" in node
    assert payload["graphs"]["execution"]["graph_kind"] == "execution"
    assert payload["graphs"]["artifact"]["graph_kind"] == "artifact"


def test_render_capture_bundle_v3_html(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        writer.ingest_claude_session(parsed)
    finally:
        writer.close()

    out = tmp_path / "bundle"
    render_capture_bundle(repo, parsed.external_id, out)
    html = (out / "index.html").read_text(encoding="utf-8")
    _assert_no_external_resources(html)
    assert "capture.js" in html
    assert "session-header" in html
    assert (out / "assets" / "capture.js").is_file()
    data = parse_cairn_data(html)
    assert data["cairn_bundle_version"] == 3
    assert data["turns"]
