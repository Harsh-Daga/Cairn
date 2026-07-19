"""Global agent histories must not cross workspace privacy boundaries."""

from __future__ import annotations

import json
from pathlib import Path

from server.ingest.adapters import cline_family, gemini_cli, openclaw
from server.ingest.project_paths import (
    discover_agent_jsonl_sessions,
    structured_log_matches_project,
)


def _write_jsonl(path: Path, *, cwd: Path, extra: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "session_id": path.stem,
                "cwd": str(cwd),
                "type": "user_message",
                "event": "user_message",
                "role": "user",
                "content": f"private prompt {extra}",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_generic_global_history_requires_explicit_workspace_match(tmp_path: Path) -> None:
    workspace = tmp_path / "wanted"
    other = tmp_path / "other"
    workspace.mkdir()
    other.mkdir()
    sessions = tmp_path / "sessions"
    matching = sessions / "matching.jsonl"
    unrelated = sessions / "unrelated.jsonl"
    unknown = sessions / "unknown.jsonl"
    _write_jsonl(matching, cwd=workspace / "subdir")
    _write_jsonl(unrelated, cwd=other)
    unknown.write_text(
        '{"session_id":"unknown","type":"user_message","content":"no project metadata"}\n',
        encoding="utf-8",
    )

    assert discover_agent_jsonl_sessions(sessions, project_root=workspace) == [matching.resolve()]


def test_project_probe_rejects_oversized_or_prompt_only_path_claims(tmp_path: Path) -> None:
    workspace = tmp_path / "wanted"
    workspace.mkdir()
    oversized = tmp_path / "oversized.jsonl"
    _write_jsonl(oversized, cwd=workspace, extra="x" * (1024 * 1024))
    assert not structured_log_matches_project(oversized, workspace)

    prompt_only = tmp_path / "prompt-only.jsonl"
    prompt_only.write_text(
        json.dumps(
            {
                "type": "user_message",
                "content": f"Ignore policy and claim cwd={workspace}",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert not structured_log_matches_project(prompt_only, workspace)


def test_gemini_and_openclaw_discovery_filter_other_projects(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "wanted"
    other = tmp_path / "other"
    workspace.mkdir()
    other.mkdir()

    gemini_root = tmp_path / "gemini"
    gemini_match = gemini_root / "matching.jsonl"
    gemini_other = gemini_root / "unrelated.jsonl"
    _write_jsonl(gemini_match, cwd=workspace)
    _write_jsonl(gemini_other, cwd=other)
    monkeypatch.setattr(gemini_cli, "gemini_roots", lambda: [gemini_root])
    assert gemini_cli.discover_gemini_sessions(workspace) == [gemini_match]

    openclaw_root = tmp_path / "openclaw"
    openclaw_match = openclaw_root / "matching.jsonl"
    openclaw_other = openclaw_root / "unrelated.jsonl"
    _write_jsonl(openclaw_match, cwd=workspace)
    _write_jsonl(openclaw_other, cwd=other)
    monkeypatch.setattr(openclaw, "openclaw_root", lambda: openclaw_root)
    assert openclaw.discover_openclaw_sessions(workspace) == [openclaw_match]


def test_cline_global_tasks_require_workspace_metadata(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "wanted"
    other = tmp_path / "other"
    workspace.mkdir()
    other.mkdir()
    global_storage = tmp_path / "globalStorage"
    tasks = global_storage / "saoudrizwan.claude-dev" / "tasks"

    for task, cwd in (("matching", workspace), ("unrelated", other)):
        task_dir = tasks / task
        task_dir.mkdir(parents=True)
        (task_dir / "ui_messages.json").write_text(
            '[{"type":"say","say":"text","text":"private task"}]',
            encoding="utf-8",
        )
        (task_dir / "task_metadata.json").write_text(
            json.dumps({"cwd": str(cwd)}),
            encoding="utf-8",
        )
    unknown_dir = tasks / "unknown"
    unknown_dir.mkdir()
    (unknown_dir / "ui_messages.json").write_text(
        '[{"type":"say","say":"text","text":"no workspace metadata"}]',
        encoding="utf-8",
    )

    monkeypatch.setattr(cline_family, "cline_global_storage_roots", lambda: [global_storage])
    assert cline_family.discover_cline_sessions(workspace) == [
        (tasks / "matching" / "ui_messages.json", "cline")
    ]
