"""§6.2 read API response-shape tests."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def test_overview_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/overview?days=90")
    assert resp.status_code == 200
    body = resp.json()
    assert "kpis" in body
    assert "narrative" in body
    assert "tail_risk" in body
    assert "data_notes" in body
    assert body["money"]["period_days"] == 90
    assert body["money"]["primary_action"] == "/optimize"
    assert body["kpis"]["traces"] >= 1


def test_overview_money_allocates_waste_cost_and_ranks_causes(
    api_client: TestClient, api_workspace: tuple
) -> None:
    root, _ws, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute(
            """UPDATE traces SET input_tokens = 800, output_tokens = 200,
               cost = 10, cost_source = 'priced', waste_tokens = 250
               WHERE trace_id = ?""",
            (trace_id,),
        )
        conn.execute(
            "UPDATE spans SET waste_category = NULL, waste_tokens = 0 WHERE trace_id = ?",
            (trace_id,),
        )
        conn.execute(
            """UPDATE spans SET waste_category = 'retry_loop', waste_tokens = 200
               WHERE trace_id = ? AND seq = 1""",
            (trace_id,),
        )
    money = api_client.get("/api/overview?days=90").json()["money"]
    assert money["total_spend_usd"] == 10
    assert money["spend_estimated"] is True
    assert money["wasted_spend_usd"] == 2.5
    assert money["wasted_spend_pct"] == 25
    assert money["waste_estimated"] is True
    assert money["top_causes"][0]["category"] == "retry_loop"
    assert money["top_causes"][0]["estimated_savings_usd"] == 2
    assert money["top_causes"][0]["fix"]


def test_weekly_recap_includes_quality_trend_and_reached_verdicts(
    api_client: TestClient, api_workspace: tuple
) -> None:
    root, ws_id, trace_id = api_workspace
    now = datetime.now(UTC)
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute(
            """UPDATE traces SET started_at = ?, cost = 4, cost_source = 'observed'
               WHERE trace_id = ?""",
            (now.isoformat(), trace_id),
        )
        conn.execute("UPDATE outcomes SET quality_score = 80 WHERE trace_id = ?", (trace_id,))
        conn.execute(
            """INSERT INTO traces (
                 trace_id, workspace_id, source, external_id, started_at, status
               ) VALUES ('recap-previous', ?, 'codex', 'recap-previous', ?, 'completed')""",
            (ws_id, (now - timedelta(days=10)).isoformat()),
        )
        conn.execute(
            "INSERT INTO outcomes (trace_id, quality_score) VALUES ('recap-previous', 60)"
        )
        conn.execute(
            """INSERT INTO evidence (
                 evidence_id, producer, produced_at, trace_ids_json, metrics_json
               ) VALUES ('recap-evidence', 'test', ?, '[]', '{}')""",
            (now.isoformat(),),
        )
        conn.execute(
            """INSERT INTO experiments (
                 experiment_id, created_at, target_file, block_key, kind, content,
                 evidence_id, status, verdict, effect_estimate, effect_ci_low,
                 effect_ci_high, measured_at
               ) VALUES (
                 'recap-experiment', ?, 'AGENTS.md', 'rule/test', 'instruction', 'test',
                 'recap-evidence', 'verdict', 'improved', 0.2, 0.1, 0.3, ?
               )""",
            (now.isoformat(), now.isoformat()),
        )
    recap = api_client.get("/api/recap")
    assert recap.status_code == 200
    body = recap.json()
    assert body["period_days"] == 7
    assert body["money"]["total_spend_usd"] == 4
    assert body["quality_trend"]["current_mean"] == 80
    assert body["quality_trend"]["previous_mean"] == 60
    assert body["quality_trend"]["delta"] == 20
    assert body["experiment_verdicts"][0]["verdict"] == "improved"


def test_traces_list_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/traces?days=90&limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert "traces" in body
    assert body["total"] >= 1
    assert body["traces"][0]["trace_id"]


def test_traces_search_total_matches_filtered_results(api_client: TestClient) -> None:
    body = api_client.get("/api/traces?q=definitely-not-a-real-session").json()
    assert body["traces"] == []
    assert body["total"] == 0


def test_traces_agent_filter_runs_in_database(api_client: TestClient, api_workspace: tuple) -> None:
    root, _ws, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute(
            "UPDATE spans SET agent_id = 'agent-main' WHERE trace_id = ? AND seq = 1",
            (trace_id,),
        )
    matching = api_client.get("/api/traces?agent=agent-main").json()
    assert matching["total"] == 1
    missing = api_client.get("/api/traces?agent=not-a-real-agent").json()
    assert missing["total"] == 0


def test_trace_detail_shape(api_client: TestClient, api_workspace: tuple) -> None:
    _root, _ws, trace_id = api_workspace
    resp = api_client.get(f"/api/traces/{trace_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace"]["trace_id"] == trace_id
    assert "spans" in body
    assert "tree" in body
    assert "links" in body
    assert len(body["spans"]) > 0
    assert "outcome" in body


def test_human_label_persists_and_updates_agreement(
    api_client: TestClient, api_workspace: tuple
) -> None:
    root, _ws, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute("UPDATE outcomes SET quality_score = 80 WHERE trace_id = ?", (trace_id,))
    response = api_client.put(
        f"/api/traces/{trace_id}/human-label",
        json={"label": "up", "note": "The change shipped cleanly."},
    )
    assert response.status_code == 200
    assert response.json()["label"] == "up"
    detail = api_client.get(f"/api/traces/{trace_id}").json()
    assert detail["outcome"]["human_label"] == "up"
    assert detail["outcome"]["human_note"] == "The change shipped cleanly."
    agreement = api_client.get("/api/workspace").json()["health"]["human_label_agreement"]
    assert agreement == {"labeled_sessions": 1, "agreements": 1, "rate": 1.0}


def test_trace_replay_shape(api_client: TestClient, api_workspace: tuple) -> None:
    _root, _ws, trace_id = api_workspace
    resp = api_client.get(f"/api/traces/{trace_id}/replay?seq=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_id"] == trace_id
    assert body["spans"] is not None
    assert body["summary"] is not None


def test_trace_replay_checkpoints_shape(api_client: TestClient, api_workspace: tuple) -> None:
    _root, _ws, trace_id = api_workspace
    resp = api_client.get(f"/api/traces/{trace_id}/replay")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_id"] == trace_id
    assert body["checkpoints"] is not None
    assert len(body["checkpoints"]) >= 1


def test_trace_replay_cost_is_cumulative(api_client: TestClient, api_workspace: tuple) -> None:
    root, _ws, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute("UPDATE traces SET cost = 8.0 WHERE trace_id = ?", (trace_id,))
    checkpoints = api_client.get(f"/api/traces/{trace_id}/replay").json()["checkpoints"]
    assert checkpoints[0]["summary"]["cost"] < 8.0
    assert checkpoints[0]["summary"]["cost_estimated"] is True
    assert checkpoints[-1]["summary"]["cost"] == 8.0
    assert checkpoints[-1]["summary"]["cost_estimated"] is False


def test_trace_diff_shape(api_client: TestClient, api_workspace: tuple) -> None:
    _root, _ws, trace_id = api_workspace
    resp = api_client.get(f"/api/traces/diff?a={trace_id}&b={trace_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["a"]["trace_id"] == trace_id
    assert body["b"]["trace_id"] == trace_id
    assert "summary" in body
    assert "turns" in body


def test_agents_shape(api_client: TestClient, api_workspace: tuple) -> None:
    root, _ws, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute("UPDATE traces SET cost = 7.5 WHERE trace_id = ?", (trace_id,))
    resp = api_client.get("/api/agents?days=90")
    assert resp.status_code == 200
    body = resp.json()
    assert "agents" in body
    assert "handoff_matrix" in body
    assert sum(agent["cost"] for agent in body["agents"]) == 7.5


def test_behavior_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/behavior?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert "series" in body
    assert "drift" in body
    assert "data_notes" in body


def test_quality_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/quality?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert "outcomes" in body
    assert "histogram" in body
    assert "cost_per_success" in body


def test_analytics_usage_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/analytics/usage?days=30&group_by=day")
    assert resp.status_code == 200
    body = resp.json()
    assert body["group_by"] == "day"
    assert "series" in body
    assert all("waste_tokens" in row for row in body["series"])


def test_analytics_regions_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/analytics/regions?days=30")
    assert resp.status_code == 200
    assert "regions" in resp.json()


def test_analytics_waste_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/analytics/waste?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert "categories" in body
    assert "total_waste_tokens" in body
    assert all(category["events"] > 0 for category in body["categories"])
    overview = api_client.get("/api/overview?days=30").json()
    assert body["total_waste_tokens"] == overview["kpis"]["waste_tokens"]
    assert sum(category["tokens"] for category in body["categories"]) == body["total_waste_tokens"]


def test_analytics_tail_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/analytics/tail?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert "tail_risk" in body
    assert "exceedances" in body


def test_insights_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/insights")
    assert resp.status_code == 200
    body = resp.json()
    assert "insights" in body
    assert "total" in body


def test_insights_expose_savings_reason_fix_and_diagnostic_classification(
    api_client: TestClient, api_workspace: tuple
) -> None:
    root, _ws, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute(
            "UPDATE traces SET peak_context_pct = 90, started_at = ? WHERE trace_id = ?",
            (datetime.now(UTC).isoformat(), trace_id),
        )
    response = api_client.post("/api/actions/optimize_propose", json={})
    assert response.status_code == 200
    rows = api_client.get("/api/insights").json()["insights"]
    assert rows
    assert all(row["fix"]["value"] for row in rows)
    assert all(
        row["savings_estimate"] is not None or row["savings_unavailable_reason"] for row in rows
    )
    assert all("diagnostic" in row for row in rows)


def test_experiments_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/experiments")
    assert resp.status_code == 200
    assert "experiments" in resp.json()


def test_search_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/search?q=user")
    assert resp.status_code == 200
    body = resp.json()
    assert body["q"] == "user"
    assert "hits" in body


def test_search_operators_filter_real_fields(api_client: TestClient) -> None:
    by_tool = api_client.get("/api/search", params={"q": "tool:grep"}).json()
    assert by_tool["total"] > 0
    assert all(hit["kind"] == "span" for hit in by_tool["hits"])

    by_source = api_client.get("/api/search", params={"q": "source:claude_code"}).json()
    assert by_source["total"] > 0

    by_error = api_client.get("/api/search", params={"q": "is:error"}).json()
    assert by_error["total"] > 0


def test_workspace_shape(api_client: TestClient, api_workspace: tuple) -> None:
    root, ws_id, _trace_id = api_workspace
    resp = api_client.get("/api/workspace")
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_id"] == ws_id
    assert body["root_path"] == str(root)
    assert "adapters" in body
    assert body["health"]["trace_count"] >= 1


def test_actions_manifest_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/actions")
    assert resp.status_code == 200
    body = resp.json()
    names = {item["name"] for item in body["actions"]}
    assert "sync" in names
    assert "check" in names
    assert "demo_seed" in names
    assert len(names) == 16


def test_action_check_runs(api_client: TestClient) -> None:
    resp = api_client.post("/api/actions/check", json={})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_openapi_validates(api_client: TestClient) -> None:
    resp = api_client.get("/api/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "Cairn"
    assert "/api/overview" in schema["paths"]
    assert "/api/traces" in schema["paths"]
    assert "/api/actions/{name}" in schema["paths"]
