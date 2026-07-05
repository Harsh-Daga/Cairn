"""Best-effort test runs for outcome capture."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from server.util.user_config import load_user_config

_TEST_TIMEOUT = 120

_PYTEST_RE = re.compile(r"(\d+)\s+passed(?:.*?,\s*(\d+)\s+failed)?", re.IGNORECASE)
_PYTEST_FAILED_RE = re.compile(r"(\d+)\s+failed", re.IGNORECASE)
_JEST_RE = re.compile(r"Tests:\s+(\d+)\s+passed(?:.*?,\s*(\d+)\s+failed)?", re.IGNORECASE)
_GO_FAIL_RE = re.compile(r"---\s+FAIL", re.IGNORECASE)
_GO_OK_RE = re.compile(r"^ok\s+", re.IGNORECASE | re.MULTILINE)


@dataclass
class TestResult:
    status: str  # "pass" | "fail" | "unknown"
    tests_run: int | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    build_status: str | None = None
    data_notes: list[str] = field(default_factory=list)


def test_command_for(project: str | None) -> str | None:
    """Return configured test command for project, or None."""
    cfg = load_user_config()
    tests = cfg.extra.get("tests")
    if not isinstance(tests, dict):
        return None
    if project and project in tests:
        return str(tests[project]) if tests[project] else None
    if "default" in tests:
        return str(tests["default"]) if tests["default"] else None
    return None


def run_tests(cwd: str | None, project: str | None) -> TestResult:
    """Run configured test command in cwd. Default OFF."""
    cmd = test_command_for(project)
    if not cmd:
        return TestResult(
            status="unknown",
            build_status="unknown",
            data_notes=[
                "configure test_command in ~/.cairn/config.toml to enable outcome tracking"
            ],
        )
    if not cwd or not Path(cwd).is_dir():
        return TestResult(
            status="unknown",
            build_status="unknown",
            data_notes=[f"cwd {cwd!r} missing; cannot run test_command"],
        )
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=_TEST_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            status="fail",
            build_status="timeout",
            data_notes=[f"test_command timed out after {_TEST_TIMEOUT}s"],
        )
    except (OSError, ValueError) as exc:
        return TestResult(
            status="unknown",
            build_status="error",
            data_notes=[f"test_command failed to execute: {exc}"],
        )

    passed, failed, run_n = _parse_counts(proc.stdout)
    notes: list[str] = [f"test_command: {cmd}"]
    if proc.returncode != 0 and failed == 0 and passed == 0:
        notes.append(f"non-zero exit ({proc.returncode}); could not parse pass/fail counts")
    status = "pass" if (proc.returncode == 0 and (failed == 0 or failed is None)) else "fail"
    build_status = "pass" if proc.returncode == 0 else "fail"
    return TestResult(
        status=status,
        tests_run=run_n,
        tests_passed=passed,
        tests_failed=failed,
        build_status=build_status,
        data_notes=notes,
    )


def _parse_counts(stdout: str) -> tuple[int | None, int | None, int | None]:
    """Parse pytest/jest/go-test output -> (passed, failed, run)."""
    if not stdout:
        return None, None, None
    match = _PYTEST_RE.search(stdout)
    if match:
        passed = int(match.group(1))
        failed = int(match.group(2)) if match.group(2) else 0
        return passed, failed, passed + failed
    match = _JEST_RE.search(stdout)
    if match:
        passed = int(match.group(1))
        failed = int(match.group(2)) if match.group(2) else 0
        return passed, failed, passed + failed
    failed_match = _PYTEST_FAILED_RE.search(stdout)
    if failed_match:
        failed = int(failed_match.group(1))
        return 0, failed, failed
    if _GO_FAIL_RE.search(stdout):
        failed = len(_GO_FAIL_RE.findall(stdout))
        return None, failed, None
    if _GO_OK_RE.search(stdout):
        return None, 0, None
    return None, None, None
