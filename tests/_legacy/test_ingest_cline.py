"""Cline family ingest tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from cairn.ingest.parsers.cline_family import parse_cline_task
from cairn.ingest.writer import CaptureWriter

_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "ingest"
    / "cline_mini"
    / "tasks"
    / "task-redacted-001"
    / "ui_messages.json"
)


def _publisher_path(tmp_path: Path, publisher: str) -> Path:
    task_dir = tmp_path / publisher / "tasks" / "task-redacted-001"
    task_dir.mkdir(parents=True)
    shutil.copy(_FIXTURE, task_dir / "ui_messages.json")
    return task_dir / "ui_messages.json"


def test_cline_publisher_labels(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    cases = {
        "saoudrizwan.claude-dev": "cline",
        "rooveterinaryinc.roo-cline": "roo",
        "kilocode.kilo-code": "kilo",
    }
    for publisher, label in cases.items():
        path = _publisher_path(tmp_path, publisher)
        parsed = parse_cline_task(path, source=label, repo_root=root)
        assert parsed is not None
        assert parsed.source == label
        writer = CaptureWriter(root)
        try:
            result = writer.ingest_cline_session(parsed)
            assert result.inserted
        finally:
            writer.close()
