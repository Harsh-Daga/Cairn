"""Ingest circuit breakers: file budgets, quarantine, pause, source untouched."""

from __future__ import annotations

import time
from pathlib import Path

from server.ingest.circuit_breakers import (
    assess_pre_parse,
    circuit_status,
    load_state,
    note_failure,
    quarantine_path,
    resume_circuits,
    run_parse_with_budget,
)
from server.util.private_files import write_private_text


def _ws(tmp_path: Path, *, toml: str = "") -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".cairn").mkdir()
    if toml:
        write_private_text(root / ".cairn" / "config.toml", toml)
    return root


def test_oversized_file_blocked_and_source_untouched(tmp_path: Path) -> None:
    root = _ws(
        tmp_path,
        toml="[resources]\nmax_file_bytes = 1024\nmax_consecutive_failures = 2\n",
    )
    src = root / "huge.jsonl"
    payload = b"x" * 2048
    src.write_bytes(payload)
    decision = assess_pre_parse(src, workspace_root=root, adapter_id="cursor")
    assert decision.allow is False
    assert decision.reason == "file_too_large"
    manifest = quarantine_path(
        root,
        adapter_id="cursor",
        path=src,
        reason=decision.reason,
        detail=decision.detail,
        file_bytes=decision.file_bytes,
    )
    assert manifest["source_untouched"] is True
    assert src.read_bytes() == payload
    assert (Path(manifest["source_path"])).is_file()
    status = circuit_status(root)
    assert status["quarantine_count"] >= 1


def test_failure_streak_pauses_adapter(tmp_path: Path) -> None:
    root = _ws(tmp_path, toml="[resources]\nmax_consecutive_failures = 3\n")
    for _ in range(3):
        note_failure(
            root,
            adapter_id="claude_code",
            reason="parse_error",
            detail="boom",
        )
    state = load_state(root)
    assert "claude_code" in state.paused_adapters
    decision = assess_pre_parse(
        root / "missing.jsonl",
        workspace_root=root,
        adapter_id="claude_code",
        state=state,
    )
    # paused before file checks
    assert decision.allow is False
    assert decision.reason == "adapter_paused"
    # other adapters still allowed (file missing → parse_error path in assess when no pause)
    other = assess_pre_parse(
        root / "ok.jsonl",
        workspace_root=root,
        adapter_id="codex",
        state=state,
    )
    # ok.jsonl doesn't exist → parse_error not allow; create small file
    (root / "ok.jsonl").write_text("{}\n", encoding="utf-8")
    other = assess_pre_parse(
        root / "ok.jsonl",
        workspace_root=root,
        adapter_id="codex",
        state=load_state(root),
    )
    assert other.allow is True
    resumed = resume_circuits(root, adapter_id="claude_code")
    assert resumed["ok"] is True
    assert "claude_code" not in load_state(root).paused_adapters


def test_parse_timeout(tmp_path: Path) -> None:
    def _slow() -> str:
        time.sleep(2.0)
        return "done"

    result, reason, detail = run_parse_with_budget(_slow, max_parse_ms=100)
    assert result is None
    assert reason == "parse_timeout"
    assert "100" in detail


def test_soft_budget_over_blocks(tmp_path: Path) -> None:
    root = _ws(tmp_path, toml="[resources]\nsoft_budget_bytes = 1\n")
    # Create some bytes under .cairn so inventory exceeds 1 byte
    write_private_text(root / ".cairn" / "pad.bin", "hello-world")
    src = root / "tiny.jsonl"
    src.write_text("x\n", encoding="utf-8")
    decision = assess_pre_parse(src, workspace_root=root, adapter_id="cursor")
    assert decision.allow is False
    assert decision.reason == "disk_budget_over"
