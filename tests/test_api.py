"""§6.2 read API response-shape tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_overview_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/overview?days=90")
    assert resp.status_code == 200
    body = resp.json()
    assert "kpis" in body
    assert "narrative" in body
    assert "tail_risk" in body
    assert "data_notes" in body
    assert body["kpis"]["traces"] >= 1


def test_traces_list_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/traces?days=90&limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert "traces" in body
    assert body["total"] >= 1
    assert body["traces"][0]["trace_id"]


def test_trace_detail_shape(api_client: TestClient, api_workspace: tuple) -> None:
    _root, _ws, trace_id = api_workspace
    resp = api_client.get(f"/api/traces/{trace_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace"]["trace_id"] == trace_id
    assert "spans" in body
    assert "tree" in body
    assert len(body["spans"]) > 0


def test_trace_replay_shape(api_client: TestClient, api_workspace: tuple) -> None:
    _root, _ws, trace_id = api_workspace
    resp = api_client.get(f"/api/traces/{trace_id}/replay?seq=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_id"] == trace_id
    assert "spans" in body
    assert "summary" in body


def test_agents_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/agents?days=90")
    assert resp.status_code == 200
    body = resp.json()
    assert "agents" in body
    assert "handoff_matrix" in body


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
    assert len(names) == 15


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
