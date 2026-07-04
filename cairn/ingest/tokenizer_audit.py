"""Tokenizer calibration audit against measured-token fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from cairn.ingest import tokenize


def run_tokenizer_check(fixtures_dir: Path | None = None) -> dict[str, object]:
    """Compare heuristic counts to measured usage in bundled ingest fixtures."""
    root = fixtures_dir or Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ingest"
    paths = sorted(root.glob("*.jsonl"))
    if not paths:
        return {"error": "no fixtures", "mean_error_pct": None}

    errors: list[float] = []
    samples = 0
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            usage = row.get("usage") or row.get("message", {}).get("usage")
            if not isinstance(usage, dict):
                continue
            measured_in = usage.get("input_tokens") or usage.get("prompt_tokens")
            text = row.get("text") or row.get("content") or ""
            if not isinstance(measured_in, int) or measured_in < 50 or not text:
                continue
            model = row.get("model") or usage.get("model")
            est, method = tokenize.count_tokens(str(text), model=model)
            if method == "exact":
                continue
            err = abs(est - measured_in) / measured_in * 100.0
            errors.append(err)
            samples += 1
            tokenize.record_exact_calibration(model, str(text), exact_tokens=measured_in)

    if not errors:
        return {"fixtures": [p.name for p in paths], "samples": 0, "mean_error_pct": None}

    mean_err = sum(errors) / len(errors)
    return {
        "fixtures": [p.name for p in paths],
        "samples": samples,
        "mean_error_pct": round(mean_err, 2),
        "max_error_pct": round(max(errors), 2),
    }
