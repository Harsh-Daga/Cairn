"""Demo workspace seeding tests."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from server.demo.scenarios import (
    DEMO_FAILURE_TRACE_INDEX,
    DEMO_MULTI_AGENT_TRACE_INDEX,
    DEMO_TAIL_TRACE_INDEX,
    trace_scenarios,
)
from server.demo.seed import seed_demo_workspace


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def test_seed_demo_workspace_is_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "demo-workspace"
    first = seed_demo_workspace(root, reset=True)
    second = seed_demo_workspace(root, reset=False)
    assert first.trace_count == 120
    assert second.trace_count == 120
    assert first.workspace_id == second.workspace_id

    conn = _connect(root / ".cairn" / "cairn.db")
    try:
        trace_total = conn.execute("SELECT COUNT(*) AS n FROM traces").fetchone()
        assert trace_total is not None
        assert int(trace_total["n"]) == 120

        actors = conn.execute("SELECT COUNT(*) AS n FROM actors").fetchone()
        assert actors is not None
        assert int(actors["n"]) == 3

        sources = conn.execute("SELECT COUNT(DISTINCT source) AS n FROM traces").fetchone()
        assert sources is not None
        assert int(sources["n"]) == 4

        expected_trace = str(
            uuid5(NAMESPACE_URL, f"cairn-demo/trace/{DEMO_MULTI_AGENT_TRACE_INDEX:03d}")
        )
        row = conn.execute(
            "SELECT trace_id FROM traces WHERE trace_id = ?",
            (expected_trace,),
        ).fetchone()
        assert row is not None

        multi_agents = conn.execute(
            """
            SELECT COUNT(DISTINCT agent_id) AS n
            FROM spans
            WHERE trace_id = ? AND agent_id IS NOT NULL
            """,
            (expected_trace,),
        ).fetchone()
        assert multi_agents is not None
        assert int(multi_agents["n"]) >= 2

        diagnostics = conn.execute("SELECT COUNT(*) AS n FROM diagnostics").fetchone()
        assert diagnostics is not None
        assert int(diagnostics["n"]) >= 1

        verdict = conn.execute(
            "SELECT status, verdict FROM experiments WHERE experiment_id = 'demo-exp-verdict-001'"
        ).fetchone()
        assert verdict is not None
        assert verdict["status"] == "verdict"
        assert verdict["verdict"] == "improved"

        max_cost = conn.execute("SELECT MAX(cost) AS c FROM traces").fetchone()
        assert max_cost is not None
        assert float(max_cost["c"]) > 10.0
    finally:
        conn.close()


def test_trace_scenario_stage_is_pure_and_pins_special_journeys() -> None:
    anchor = datetime(2026, 7, 18, 12, tzinfo=UTC)

    first = trace_scenarios(anchor)
    second = trace_scenarios(anchor)

    assert first == second
    assert len(first) == 120
    assert first[DEMO_FAILURE_TRACE_INDEX].status == "error"
    assert first[DEMO_MULTI_AGENT_TRACE_INDEX].index == DEMO_MULTI_AGENT_TRACE_INDEX
    assert first[DEMO_TAIL_TRACE_INDEX].cost == 14.75
    assert first[DEMO_TAIL_TRACE_INDEX].waste_tokens == 3100


def test_cli_demo_seed_uses_home_workspace(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "server.cli", "demo", "--reset"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert '"trace_count": 120' in result.stdout
    assert '"source_count": 4' in result.stdout
    db_path = tmp_path / ".cairn-demo" / ".cairn" / "cairn.db"
    assert db_path.is_file()
