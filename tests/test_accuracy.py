"""Accuracy artifact generation tests."""

from __future__ import annotations

import json

from scripts import gen_accuracy


def test_accuracy_covers_every_adapter_fixture() -> None:
    rows = gen_accuracy.measure()

    assert len(rows) == 12
    assert {str(row["adapter_id"]) for row in rows} == {
        "aider",
        "claude_code",
        "cline",
        "codex",
        "cursor",
        "gemini_cli",
        "goose",
        "hermes",
        "kilo",
        "openclaw",
        "opencode",
        "roo",
    }
    assert all(row["parse_coverage_pct"] == 100.0 for row in rows)
    assert "Fixture parse coverage" in gen_accuracy.render(rows)


def test_packaged_accuracy_data_matches_generator() -> None:
    rows = gen_accuracy.measure()
    packaged = json.loads(gen_accuracy.DATA_OUT.read_text(encoding="utf-8"))

    assert set(packaged) == {str(row["adapter_id"]) for row in rows}
    for row in rows:
        assert packaged[str(row["adapter_id"])]["parse_coverage_pct"] == row["parse_coverage_pct"]
