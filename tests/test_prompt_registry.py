"""Phase 6 prompt registry tests."""

from __future__ import annotations

from pathlib import Path

from cairn.prompts.registry import PromptRegistry, parse_prompt_ref


def test_parse_prompt_ref() -> None:
    assert parse_prompt_ref("summarize") == ("summarize", None)
    assert parse_prompt_ref("summarize@v2") == ("summarize", "v2")


def test_prompt_sync_registers_versions(project_dir: Path) -> None:
    registry = PromptRegistry(project_dir)
    try:
        first = registry.sync()
        assert len(first) >= 3
        assert all(e.version == "v1" for e in first)
        second = registry.sync()
        assert second == []
        entries = registry.list_entries()
        assert len(entries) >= 3
        shown = registry.get("summarize", "v1")
        assert shown is not None
        assert "Summarize the document" in shown.body
    finally:
        registry.close()


def test_prompt_sync_new_version_on_change(project_dir: Path) -> None:
    registry = PromptRegistry(project_dir)
    try:
        registry.sync()
        prompt_path = project_dir / "prompts" / "summarize.md"
        text = prompt_path.read_text(encoding="utf-8")
        prompt_path.write_text(text + "\n<!-- changed -->\n", encoding="utf-8")
        updated = registry.sync()
        assert len(updated) == 1
        assert updated[0].version == "v2"
        diff = registry.diff("summarize@v1", "summarize@v2")
        assert "changed" in diff
    finally:
        registry.close()


def test_prompt_cli_sync(project_dir: Path) -> None:
    from cairn.cli.prompt_cmd import run

    class Args:
        project = project_dir
        prompt_command = "sync"
        json = True
        ref = ""
        left = ""
        right = ""

    assert run(Args()) == 0
