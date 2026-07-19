"""Deterministic examples stay current and provider-free."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from server.configuration import load_config
from server.demo.seed import seed_demo_workspace
from server.ingest.otlp import parse_otlp_json

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
E2E = EXAMPLES / "e2e-demo"
RETIRED_CMD = re.compile(r"`cairn (init|validate|build|profile|behavior|outcomes|advanced)\b")


def test_examples_index_and_dirs_exist() -> None:
    assert (EXAMPLES / "README.md").is_file()
    for name in ("e2e-demo", "ci-gate", "otlp-ingest", "mcp-setup", "export-archive"):
        assert (EXAMPLES / name / "README.md").is_file(), name


def test_examples_markdown_avoids_retired_commands() -> None:
    violations: list[str] = []
    for path in EXAMPLES.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if RETIRED_CMD.search(text) or "docs/guides/" in text:
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, f"Stale example docs: {violations}"


def test_e2e_demo_sample_config_loads(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    (workspace / ".cairn").mkdir(parents=True)
    shutil.copy(E2E / "cairn.toml", workspace / ".cairn" / "config.toml")
    cfg = load_config(workspace)
    assert cfg.budgets.min_quality == 0.65
    assert cfg.collection.mode == "manual"
    assert cfg.storage.mode == "balanced"


def test_e2e_demo_setup_script(tmp_path: Path) -> None:
    dest = tmp_path / "demo-copy"
    result = subprocess.run(
        ["bash", str(E2E / "setup.sh"), str(dest)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (dest / ".cairn" / "config.toml").is_file()
    assert "cairn demo --reset" in result.stdout


def test_deterministic_demo_check_action(tmp_path: Path) -> None:
    workspace = tmp_path / "demo"
    seed_demo_workspace(workspace, reset=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "server.cli",
            "check",
            "--workspace",
            str(workspace),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode in {0, 1}, result.stderr
    payload = json.loads(result.stdout)
    assert "ok" in payload


def test_otlp_example_sample_parses() -> None:
    sample = EXAMPLES / "otlp-ingest" / "sample_trace.json"
    fixture = ROOT / "tests" / "fixtures" / "otlp" / "sample_trace.json"
    assert sample.read_bytes() == fixture.read_bytes()
    traces = parse_otlp_json(json.loads(sample.read_text(encoding="utf-8")))
    assert len(traces) == 1


def test_ci_gate_snippet_mentions_check() -> None:
    text = (EXAMPLES / "ci-gate" / "github-actions.yml").read_text(encoding="utf-8")
    assert "cairn check" in text
    assert "cairn sync" in text
