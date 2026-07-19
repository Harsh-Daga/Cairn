"""Budget burn math, analytics API, and CLI stats."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from server.analyze.budget_burn import compute_budget_burn
from server.api.payloads import build_budget_analytics
from server.cli import app
from server.store.db import connect
from server.store.migrate import migrate
from server.util.ids import new_ulid


def _seed_month_days(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int,
    cost_per_day: float,
    now: datetime,
) -> None:
    for offset in range(days):
        started = (now - timedelta(days=offset)).replace(hour=12, minute=0, second=0, microsecond=0)
        conn.execute(
            """
            INSERT INTO traces (
              trace_id, workspace_id, source, external_id, started_at, status, cost, model
            ) VALUES (?, ?, 'codex', ?, ?, 'completed', ?, ?)
            """,
            (
                f"burn-{offset}",
                workspace_id,
                f"burn-{offset}",
                started.isoformat(),
                cost_per_day,
                "gpt-test",
            ),
        )
    conn.commit()


def _fresh_workspace(tmp_path: Path) -> tuple[sqlite3.Connection, str]:
    db_path = tmp_path / "cairn.db"
    conn = connect(db_path)
    migrate(conn)
    workspace_id = new_ulid()
    conn.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) VALUES (?, ?, ?, ?)",
        (workspace_id, str(tmp_path), "burn", datetime.now(UTC).isoformat()),
    )
    conn.commit()
    return conn, workspace_id


def test_compute_budget_burn_insufficient_history(tmp_path: Path) -> None:
    conn, workspace_id = _fresh_workspace(tmp_path)
    now = datetime(2026, 7, 18, 15, 0, tzinfo=UTC)
    _seed_month_days(conn, workspace_id=workspace_id, days=3, cost_per_day=1.0, now=now)

    burn = compute_budget_burn(
        conn,
        workspace_id=workspace_id,
        monthly_limit_usd=100.0,
        timezone="UTC",
        now=now,
    )
    assert burn.projection_state == "insufficient_history"
    assert burn.linear_projected_usd is None
    assert burn.projected_overrun_date is None
    assert burn.month_spend_usd == 3.0
    conn.close()


def test_compute_budget_burn_projections_and_overrun(tmp_path: Path) -> None:
    conn, workspace_id = _fresh_workspace(tmp_path)
    now = datetime(2026, 7, 18, 15, 0, tzinfo=UTC)
    _seed_month_days(conn, workspace_id=workspace_id, days=10, cost_per_day=2.0, now=now)

    burn = compute_budget_burn(
        conn,
        workspace_id=workspace_id,
        monthly_limit_usd=25.0,
        timezone="UTC",
        now=now,
    )
    assert burn.projection_state == "available"
    assert burn.linear_projected_usd is not None
    assert burn.trailing_7d_projected_usd is not None
    assert burn.projected_overrun_date is not None
    assert burn.model_shares
    assert burn.model_shares[0].key == "gpt-test"
    conn.close()


def test_analytics_budget_endpoint(api_client, api_workspace: tuple) -> None:
    root, workspace_id, _trace_id = api_workspace
    config_path = root / ".cairn" / "config.toml"
    config_path.write_text("[budgets]\nmonthly_usd = 50\n", encoding="utf-8")
    now = datetime.now(UTC)
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        for offset in range(10):
            started = (now - timedelta(days=offset)).isoformat()
            conn.execute(
                """
                INSERT INTO traces (
                  trace_id, workspace_id, source, external_id, started_at, status, cost, model
                ) VALUES (?, ?, 'codex', ?, ?, 'completed', 1.5, 'model-a')
                """,
                (f"api-burn-{offset}", workspace_id, f"api-burn-{offset}", started),
            )

    body = api_client.get("/api/analytics/budget?days=30").json()
    assert body["budget_state"] in {"healthy", "attention", "over"}
    assert body["month_spend_usd"] >= 10.0
    assert body["ledger"]["conclusion"]
    assert isinstance(body["limitations"], list)
    assert "model_shares" in body


def test_build_budget_analytics_unconfigured(api_workspace: tuple) -> None:
    root, workspace_id, _trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.row_factory = sqlite3.Row
        payload = build_budget_analytics(conn, workspace_id=workspace_id)
    assert payload.budget_state == "unconfigured"
    assert payload.ledger.next_action_href == "/settings?tab=budget"


def test_cairn_stats_json(api_workspace: tuple, monkeypatch) -> None:
    root, _workspace_id, _trace_id = api_workspace
    (root / ".cairn" / "config.toml").write_text(
        "[budgets]\nmonthly_usd = 10\nweekly_usd = 5\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    runner = CliRunner()
    result = runner.invoke(app, ["stats", "--json", "--workspace", str(root)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "cairn.stats.v1"
    assert payload["generated_at"]
    assert payload["timezone"]
    assert "month_spend_usd" in payload
    assert payload["monthly_limit_usd"] == 10.0
