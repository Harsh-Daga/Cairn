"""Coverage baseline and report-gate behavior."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import check_coverage


def test_coverage_baseline_matches_documented_exclusions() -> None:
    baseline = json.loads(check_coverage.BASELINE.read_text(encoding="utf-8"))
    assert baseline["changed_lines_min_pct"] == 90.0
    assert baseline["python"]["branches_pct"] > 0
    assert baseline["ui"]["branches_pct"] > 0
    assert "server/static/**" in baseline["exclusions"]["python"]
    assert "ui/src/lib/generated/**" in baseline["exclusions"]["ui"]


def test_lcov_line_parser_merges_multiple_statements_on_one_line(tmp_path: Path) -> None:
    report = tmp_path / "coverage.lcov"
    report.write_text(
        "\n".join(
            (
                f"SF:{check_coverage.ROOT / 'server' / 'sample.py'}",
                "DA:10,0",
                "DA:10,1",
                "DA:11,0",
                "end_of_record",
            )
        ),
        encoding="utf-8",
    )
    assert check_coverage._lcov_lines(report) == {"server/sample.py": {10: True, 11: False}}


def test_baseline_gate_reports_regression(tmp_path: Path, monkeypatch) -> None:
    baseline = tmp_path / "baseline.json"
    python = tmp_path / "python.json"
    ui = tmp_path / "ui.json"
    baseline.write_text(
        json.dumps(
            {
                "python": {"statements_pct": 80, "branches_pct": 60},
                "ui": {"statements_pct": 30, "branches_pct": 20},
            }
        ),
        encoding="utf-8",
    )
    python.write_text(
        json.dumps(
            {
                "totals": {
                    "percent_statements_covered": 79,
                    "percent_branches_covered": 61,
                }
            }
        ),
        encoding="utf-8",
    )
    ui.write_text(
        json.dumps(
            {
                "total": {
                    "statements": {"pct": 31},
                    "branches": {"pct": 21},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(check_coverage, "BASELINE", baseline)
    monkeypatch.setattr(check_coverage, "PYTHON_JSON", python)
    monkeypatch.setattr(check_coverage, "UI_SUMMARY", ui)
    assert check_coverage.check_baselines() == [
        "python.statements_pct 79.00% is below observed baseline 80.00%"
    ]
