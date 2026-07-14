"""Focused adapter doctor tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from server.cli import app
from server.ingest.adapter_doctor import format_adapter_doctor, run_adapter_doctor

FIXTURE = Path(__file__).parent / "fixtures" / "ingest" / "claude_code_mini.jsonl"


def test_adapter_doctor_reports_shape_parse_and_accuracy(tmp_path: Path) -> None:
    result = run_adapter_doctor("claude_code", tmp_path, sample_path=FIXTURE)

    assert result["ok"] is True
    assert result["parsed"] is True
    assert result["normalized_events"] > 0
    assert result["unknown_fields"] == {}
    assert result["token_accuracy"] == {
        "method": "measured",
        "mape_pct": 0.0,
        "note": "assistant usage block",
    }
    output = format_adapter_doctor(result)
    assert "recognized fields" in output
    assert "MAPE 0.00%" in output


def test_adapter_doctor_identifies_unparsed_unknown_fields(tmp_path: Path) -> None:
    sample = tmp_path / "changed.jsonl"
    records = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
    records[0]["upstream_v2"] = True
    sample.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")

    result = run_adapter_doctor("claude_code", tmp_path, sample_path=sample)

    assert result["ok"] is False
    assert result["unknown_fields"] == {"upstream_v2": 1}
    assert "upstream_v2×1" in format_adapter_doctor(result)


def test_adapter_doctor_cli_command(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "adapter",
            "doctor",
            "claude_code",
            "--workspace",
            str(tmp_path),
            "--sample",
            str(FIXTURE),
        ],
    )

    assert result.exit_code == 0
    assert "sample fully parsed" in result.stdout
