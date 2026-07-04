"""Phase 6 — tokenizer calibration audit command."""

from __future__ import annotations

import json
import subprocess
import sys

from cairn.ingest.tokenizer_audit import run_tokenizer_check


def test_tokenizer_check_runs_without_crash() -> None:
    report = run_tokenizer_check()
    assert "mean_error_pct" in report
    assert report.get("samples", 0) >= 0


def test_advanced_tokenizer_check_cli() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "cairn.cli.main", "advanced", "tokenizer-check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert "mean_error_pct" in data
    if data.get("samples", 0) > 0:
        assert float(data["mean_error_pct"]) < 20.0
