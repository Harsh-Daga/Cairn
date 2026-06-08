"""Phase 5 project context system tests."""

from __future__ import annotations

from pathlib import Path

from cairn.context.config import load_context_config
from cairn.context.registry import ContextRegistry
from cairn.ledger.storage import list_context_assets


def test_load_context_config_defaults_without_toml(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Hi", encoding="utf-8")
    config = load_context_config(tmp_path)
    assert "**/*.md" in config.include
    assert ".cairn/**" in config.exclude


def test_context_scan_indexes_files(project_dir: Path) -> None:
    registry = ContextRegistry(project_dir)
    try:
        assets = registry.scan()
        assert len(assets) > 0
        paths = {a.path_rel for a in assets}
        assert any("inputs/" in p for p in paths)
        stored = list_context_assets(registry.connection)
        assert len(stored) == len(assets)
    finally:
        registry.close()


def test_context_resolve_exact_and_glob(project_dir: Path) -> None:
    registry = ContextRegistry(project_dir)
    try:
        registry.scan()
        spec = registry.resolve("inputs/spec.md")
        assert spec is not None
        assert spec.path_rel == "inputs/spec.md"
        globbed = registry.resolve("inputs/*.md")
        assert globbed is not None
        assert globbed.path_rel.startswith("inputs/")
    finally:
        registry.close()


def test_context_cli_scan_and_list(project_dir: Path) -> None:
    from cairn.cli.context_cmd import run

    class Args:
        project = project_dir
        context_command = "scan"
        json = True
        selector = ""

    code = run(Args())
    assert code == 0

    class ListArgs:
        project = project_dir
        context_command = "list"
        json = True
        selector = ""

    code = run(ListArgs())
    assert code == 0
