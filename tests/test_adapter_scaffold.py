"""Adapter scaffold tests."""

from __future__ import annotations

from pathlib import Path

from server.ingest.scaffold import scaffold_adapter


def test_scaffold_adapter_creates_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "server" / "ingest" / "adapters").mkdir(parents=True)
    (repo / "tests" / "fixtures" / "ingest").mkdir(parents=True)

    created = scaffold_adapter(repo, "demo_bot")
    assert len(created) == 3
    assert (repo / "server" / "ingest" / "adapters" / "demo_bot_adapter.py").is_file()
    assert (repo / "tests" / "fixtures" / "ingest" / "demo_bot_mini.jsonl").is_file()
    assert (repo / "tests" / "test_ingest_demo_bot.py").is_file()
