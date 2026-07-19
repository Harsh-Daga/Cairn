"""Enforce observed coverage floors and high coverage on changed executable lines."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "plans" / "v1.2.0-coverage-baseline.json"
PYTHON_JSON = ROOT / "test-results" / "coverage-python.json"
PYTHON_LCOV = ROOT / "test-results" / "coverage-python.lcov"
UI_SUMMARY = ROOT / "ui" / "coverage" / "coverage-summary.json"
UI_LCOV = ROOT / "ui" / "coverage" / "lcov.info"

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Missing coverage report: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def check_baselines() -> list[str]:
    baseline = _read_json(BASELINE)
    python = _read_json(PYTHON_JSON)["totals"]
    ui = _read_json(UI_SUMMARY)["total"]
    observed = {
        "python.statements_pct": float(python["percent_statements_covered"]),
        "python.branches_pct": float(python["percent_branches_covered"]),
        "ui.statements_pct": float(ui["statements"]["pct"]),
        "ui.branches_pct": float(ui["branches"]["pct"]),
    }
    failures: list[str] = []
    for key, actual in observed.items():
        section, metric = key.split(".")
        expected = float(baseline[section][metric])
        if actual + 1e-9 < expected:
            failures.append(f"{key} {actual:.2f}% is below observed baseline {expected:.2f}%")
    print("Coverage: " + ", ".join(f"{key}={value:.2f}%" for key, value in observed.items()))
    return failures


def _lcov_lines(path: Path) -> dict[str, dict[int, bool]]:
    if not path.is_file():
        raise ValueError(f"Missing LCOV report: {path.relative_to(ROOT)}")
    result: dict[str, dict[int, bool]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("SF:"):
            source = raw[3:]
            source_path = Path(source)
            try:
                current = source_path.resolve().relative_to(ROOT).as_posix()
            except ValueError:
                marker = "/ui/src/"
                current = f"ui/src/{source.split(marker, 1)[1]}" if marker in source else None
        elif raw.startswith("DA:") and current is not None:
            line_raw, count_raw, *_ = raw[3:].split(",")
            line = int(line_raw)
            covered = int(count_raw) > 0
            result.setdefault(current, {})[line] = (
                result.setdefault(current, {}).get(line, False) or covered
            )
    return result


def _changed_lines(base: str) -> dict[str, set[int]]:
    command = [
        "git",
        "diff",
        "--unified=0",
        "--no-ext-diff",
        f"{base}...HEAD",
        "--",
        "server",
        "ui/src",
    ]
    proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise ValueError(f"Cannot compare coverage with {base}: {proc.stderr.strip()}")
    changed: dict[str, set[int]] = {}
    current: str | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        match = _HUNK_RE.match(line)
        if current is None or match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        changed.setdefault(current, set()).update(range(start, start + count))
    return changed


def check_changed_lines(base: str) -> list[str]:
    executable = _lcov_lines(PYTHON_LCOV)
    for path, lines in _lcov_lines(UI_LCOV).items():
        executable[path] = lines
    changed = _changed_lines(base)
    relevant: list[bool] = []
    for path, lines in changed.items():
        coverage = executable.get(path, {})
        relevant.extend(coverage[line] for line in lines if line in coverage)
    if not relevant:
        print(f"Changed-line coverage: no executable changed lines against {base}")
        return []
    actual = sum(relevant) / len(relevant) * 100
    expected = float(_read_json(BASELINE)["changed_lines_min_pct"])
    print(
        f"Changed-line coverage: {actual:.2f}% "
        f"({sum(relevant)}/{len(relevant)}) against {base}; required {expected:.2f}%"
    )
    if actual + 1e-9 < expected:
        return [f"changed-line coverage {actual:.2f}% is below {expected:.2f}%"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="Git base SHA/ref for changed-line coverage")
    args = parser.parse_args()
    try:
        failures = check_baselines()
        if args.base:
            failures.extend(check_changed_lines(args.base))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Coverage gate error: {exc}")
        return 2
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("Coverage ratchet passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
