"""§6.2 read API response-shape tests."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2 as httpx
from fastapi.testclient import TestClient


def test_public_query_bounds_use_one_actionable_error_shape(api_client: TestClient) -> None:
    cases = [
        "/api/overview?days=0",
        "/api/overview?days=366",
        "/api/traces?limit=-1",
        "/api/traces?limit=201",
        "/api/traces?offset=-1",
        "/api/search?limit=0",
        f"/api/search?q={'x' * 501}",
    ]
    for path in cases:
        response = api_client.get(path)
        assert response.status_code == 422, path
        body = response.json()
        assert "detail" not in body
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["message"] == "Request parameters are invalid"
        assert body["error"]["details"]


def test_http_exception_is_not_nested_under_detail(api_client: TestClient) -> None:
    response = api_client.get("/api/traces/not-a-real-trace")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Trace not-a-real-trace not found"}
    }


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
    assert set(body["hero"]["deltas"]) == {"sessions", "spend", "waste_rate", "quality"}
    assert body["hero"]["projection"]["state"] in {
        "available",
        "insufficient_history",
        "not_current_period",
    }
    assert body["hero"]["projection"]["explanation"]
    assert isinstance(body["hero"]["quality_sparkline"], list)
    assert [shield["shield"] for shield in body["shields"]] == [
        "verification",
        "scope",
        "privacy",
        "resource",
    ]
    assert all(shield["facts"] and shield["limitation"] for shield in body["shields"])
    assert all(shield["state"] != "healthy" for shield in body["shields"])
    assert [category["category"] for category in body["attention"]] == [
        "failed_outcomes",
        "verification_debt",
        "unsupported_claims",
        "drift",
        "retry_storms",
        "parse_health",
        "budget",
        "decayed_rules",
    ]
    assert {category["state"] for category in body["attention"]} <= {
        "attention",
        "clear",
        "unavailable",
    }
    for cause in body["money"]["top_causes"]:
        assert cause["confidence"] in {"low", "medium"}
        assert cause["confidence_explanation"]
        assert cause["evidence_count"] >= len(cause["evidence"])
        for evidence in cause["evidence"]:
            assert evidence["trace_id"]
            assert evidence["label"]
            assert "text_inline" not in evidence


def test_overview_uses_typed_monthly_budget(api_client: TestClient, api_workspace: tuple) -> None:
    root, workspace_id, _trace_id = api_workspace
    config_path = root / ".cairn" / "config.toml"
    config_path.write_text("[budgets]\nmonthly_usd = 0.0001\n", encoding="utf-8")
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute(
            """
            INSERT INTO traces (
              trace_id, workspace_id, source, external_id, started_at, status, cost
            ) VALUES ('budget-current', ?, 'codex', 'budget-current', ?, 'completed', 1.0)
            """,
            (workspace_id, datetime.now(UTC).isoformat()),
        )

    body = api_client.get("/api/overview?days=90").json()

    assert body["hero"]["budget"]["monthly_limit_usd"] == 0.0001
    assert body["hero"]["budget"]["state"] == "over"
    assert "measured spend" in body["hero"]["budget"]["explanation"].lower()
    budget_attention = next(
        category for category in body["attention"] if category["category"] == "budget"
    )
    assert budget_attention["state"] == "attention"
    assert budget_attention["items"][0]["action_path"] == "/settings"


def test_overview_attention_has_bounded_evidence_deep_links(
    api_client: TestClient, api_workspace: tuple
) -> None:
    root, workspace_id, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute(
            "UPDATE outcomes SET tests_failed = 2, build_status = 'failed' WHERE trace_id = ?",
            (trace_id,),
        )
        conn.execute(
            """
            UPDATE spans SET waste_category = 'retry_loop', waste_tokens = 1
            WHERE span_id IN (
              SELECT span_id FROM spans WHERE trace_id = ? ORDER BY seq LIMIT 2
            )
            """,
            (trace_id,),
        )
        conn.execute(
            """
            INSERT INTO adapter_parse_health (
              workspace_id, adapter_id, attempts, fully_parsed, degraded, skipped, updated_at
            ) VALUES (?, 'fixture-adapter', 4, 2, 1, 1, ?)
            """,
            (workspace_id, datetime.now(UTC).isoformat()),
        )

    attention = {
        category["category"]: category
        for category in api_client.get("/api/overview?days=90").json()["attention"]
    }

    assert attention["failed_outcomes"]["state"] == "attention"
    assert attention["failed_outcomes"]["items"][0]["action_path"] == f"/sessions/{trace_id}"
    assert attention["retry_storms"]["state"] == "attention"
    assert attention["retry_storms"]["items"][0]["action_path"].startswith(
        f"/sessions/{trace_id}?span="
    )
    assert attention["parse_health"]["state"] == "attention"
    assert attention["parse_health"]["items"][0]["action_path"] == "/settings"
    assert attention["unsupported_claims"]["state"] == "unavailable"
    assert attention["decayed_rules"]["state"] == "clear"
    assert attention["decayed_rules"]["count"] == 0
    assert all(len(category["items"]) <= 3 for category in attention.values())


def test_custom_range_is_half_open_and_usage_does_not_include_boundary_days(
    api_client: TestClient, api_workspace: tuple
) -> None:
    root, workspace_id, _trace_id = api_workspace
    rows = [
        ("range-before", "2026-06-30T23:59:59+00:00", 1),
        ("range-start", "2026-07-01T00:00:00+00:00", 10),
        ("range-middle", "2026-07-01T12:00:00+00:00", 20),
        ("range-end", "2026-07-02T00:00:00+00:00", 40),
    ]
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.executemany(
            """
            INSERT INTO traces (
              trace_id, workspace_id, source, external_id, started_at, status,
              input_tokens, output_tokens, waste_tokens, cost
            ) VALUES (?, ?, 'codex', ?, ?, 'completed', ?, 0, 0, 0)
            """,
            [
                (trace_id, workspace_id, trace_id, started_at, tokens)
                for trace_id, started_at, tokens in rows
            ],
        )

    query = "start=2026-07-01T00:00:00Z&end=2026-07-02T00:00:00Z&timezone=UTC"
    overview = api_client.get(f"/api/overview?{query}")
    assert overview.status_code == 200
    assert overview.json()["kpis"]["traces"] == 2
    assert overview.json()["resolved_range"]["start"] == "2026-07-01T00:00:00+00:00"
    assert overview.json()["resolved_range"]["end"] == "2026-07-02T00:00:00+00:00"

    usage = api_client.get(f"/api/analytics/usage?{query}&group_by=day")
    assert usage.status_code == 200
    assert usage.json()["series"] == [
        {
            "key": "2026-07-01",
            "input_tokens": 30,
            "output_tokens": 0,
            "waste_tokens": 0,
            "cost": 0.0,
            "traces": 2,
        }
    ]


def test_ambiguous_http_time_range_is_actionable(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/overview?days=7&start=2026-07-01T00:00:00Z&end=2026-07-02T00:00:00Z&timezone=UTC"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_time_range"


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
        conn.execute("INSERT INTO outcomes (trace_id, quality_score) VALUES ('recap-previous', 60)")
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
    assert body["period_kind"] == "rolling_7d"
    assert body["timezone"] == "UTC"
    assert body["period_start"]
    assert body["period_end"]
    assert "cost_per_success_trend" in body
    assert "limitations" in body
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
    row = body["traces"][0]
    assert row["trace_id"]
    assert row["verification_state"] in {"verified", "failed", "debt", "unverified", "unknown"}
    assert row["data_quality_state"] in {"measured", "partial", "degraded", "unavailable"}
    assert isinstance(row["token_flow"], list)
    assert isinstance(row["top_files"], list)


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
    assert [shield["shield"] for shield in body["shields"]] == [
        "verification",
        "scope",
        "privacy",
        "resource",
    ]
    assert all(shield["facts"] and shield["limitation"] for shield in body["shields"])
    assert "links" in body
    assert len(body["spans"]) > 0
    assert "outcome" in body
    assert body["mcp_consultations"] == []


def test_trace_detail_includes_mcp_consultations(
    api_client: TestClient, api_workspace: tuple
) -> None:
    root, ws_id, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute(
            """INSERT INTO mcp_consultations (
                 event_id, workspace_id, trace_id, after_seq, tool_name, called_at, imported_at
               ) VALUES ('event-1', ?, ?, 3, 'cairn_should_i_stop',
                         '2026-01-01T00:03:00Z', '2026-01-01T00:04:00Z')""",
            (ws_id, trace_id),
        )
    body = api_client.get(f"/api/traces/{trace_id}").json()
    assert body["mcp_consultations"] == [
        {
            "event_id": "event-1",
            "trace_id": trace_id,
            "after_seq": 3,
            "tool_name": "cairn_should_i_stop",
            "called_at": "2026-01-01T00:03:00Z",
        }
    ]


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
    assert body["ledger"]["sample_size"] >= 1
    assert body["ledger"]["conclusion"]
    assert "trend" in body
    assert "coverage" in body
    assert body["limitations"]
    assert abs(sum(agent["cost"] for agent in body["agents"]) - 7.5) < 1e-6
    assert all("sample_size" in agent for agent in body["agents"])


def test_behavior_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/behavior?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert "series" in body
    assert "drift" in body
    assert "data_notes" in body
    assert body["ledger"]["conclusion"]
    assert "fingerprint_sessions" in body["ledger"]
    assert body["limitations"]
    assert any("guard" in note.lower() for note in body["limitations"])
    for event in body["drift"]:
        assert "sample_size" in event


def test_quality_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/quality?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert "outcomes" in body
    assert "histogram" in body
    assert "cost_per_success" in body
    assert body["ledger"]["conclusion"]
    assert "verified_completion_rate" in body["ledger"]
    assert body["ledger"]["unsupported_claim_rate"] is None
    assert "trend" in body
    assert "components" in body
    assert "investigations" in body
    assert "calibration" in body
    assert body["limitations"]
    assert any("process-quality" in note.lower() for note in body["limitations"])
    assert any("unsupported" in note.lower() for note in body["limitations"])
    for outcome in body["outcomes"]:
        assert "verification_state" in outcome


def test_analytics_usage_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/analytics/usage?days=30&group_by=day")
    assert resp.status_code == 200
    body = resp.json()
    assert body["group_by"] == "day"
    assert "series" in body
    assert all("waste_tokens" in row for row in body["series"])


def test_analytics_regions_shape(
    api_client: TestClient,
    api_workspace: tuple[Path, str, str],
) -> None:
    from server.models.context_region import ContextRegion
    from server.store.repos.context_regions import ContextRegionRepo
    from server.store.repos.spans import SpanRepo

    _root, _workspace_id, trace_id = api_workspace
    conn = api_client.app.state.runtime.database.reader
    spans = SpanRepo.list_by_trace(conn, trace_id)
    assert len(spans) >= 2
    ContextRegionRepo.upsert_many(
        conn,
        [
            ContextRegion(
                span_id=spans[0].span_id,
                region="tool_result",
                tokens=100,
                cost=0.10,
                content_hash="same-content-hash",
            ),
            ContextRegion(
                span_id=spans[1].span_id,
                region="tool_result",
                tokens=120,
                cost=0.12,
                content_hash="same-content-hash",
            ),
            ContextRegion(
                span_id=spans[0].span_id,
                region="tool_schema",
                tokens=20,
                cost=0.02,
                content_hash="schema-hash",
            ),
        ],
    )
    SpanRepo.update(
        conn,
        spans[0].model_copy(update={"cache_read_tokens": 50, "cache_creation_tokens": 10}),
    )
    conn.commit()

    resp = api_client.get("/api/analytics/regions?days=365")
    assert resp.status_code == 200
    body = resp.json()
    assert body["regions"]
    assert body["trend"]
    assert body["schema_overhead_tokens"] >= 20
    ledger = body["ledger"]
    assert ledger["mapped_region_tokens"] >= 240
    assert ledger["estimated_rebilled_tokens"] == 100
    assert ledger["schema_overhead_tokens"] >= 20
    assert ledger["cache_savings_available"] is False
    assert ledger["conclusion"]
    assert ledger["next_action"]
    assert "mapped region" in ledger["limitation"].lower() or "avoidable" in ledger["limitation"]
    repeated = next(
        block for block in body["rebilled_blocks"] if block["block_id"] == "block-same-content"
    )
    assert repeated["estimated_rebilled_tokens"] == 100
    assert repeated["evidence"]["trace_id"] == trace_id
    assert body["cache_trend"][0]["measured_sessions"] >= 1
    assert all(point["estimated_savings_usd"] is None for point in body["cache_trend"])
    assert "provider cache pricing" in body["cache_trend"][0]["limitation"]
    assert body["agents"]
    assert body["coverage"][0]["region_sessions"] == 1
    assert body["limitations"]
    assert any("not a partition" in note for note in body["limitations"])


def test_analytics_tools_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/analytics/tools?days=365")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ledger"]["invocations"] >= 1
    assert body["ledger"]["distinct_tools"] >= 1
    assert body["tools"]
    assert {tool["family"] for tool in body["tools"]} <= {"builtin", "mcp", "shell", "unknown"}
    assert all(tool["estimate_kind"] == "token_share" for tool in body["tools"])
    assert body["coverage"]
    assert body["limitations"]
    assert any("normalized" in note.lower() for note in body["limitations"])


def test_analytics_compare_shape(
    api_client: TestClient,
    api_workspace: tuple[Path, str, str],
) -> None:
    _root, _workspace_id, trace_id = api_workspace
    conn = api_client.app.state.runtime.database.reader
    conn.execute(
        "UPDATE traces SET difficulty_bucket = ?, difficulty = ? WHERE trace_id = ?",
        ("standard", 0.4, trace_id),
    )
    conn.commit()

    resp = api_client.get("/api/analytics/compare?days=365")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ledger"]["min_sample"] == 5
    assert body["ledger"]["cells_total"] >= 1
    assert body["ledger"]["declared_winner"] is None or isinstance(
        body["ledger"]["declared_winner"], str
    )
    assert body["cells"]
    assert all("difficulty_bucket" in cell for cell in body["cells"])
    assert all("cost_per_session" in cell for cell in body["cells"])
    assert all("verified_success_rate" in cell for cell in body["cells"])
    assert all("correction_burden_rate" in cell for cell in body["cells"])
    assert "pairwise" in body
    assert body["limitations"]
    notes = " ".join(body["limitations"]).lower()
    assert "winner" in notes or "descriptive" in notes


def test_analytics_files_shape(
    api_client: TestClient,
    api_workspace: tuple[Path, str, str],
) -> None:
    from server.store.repos.spans import SpanRepo

    _root, _workspace_id, trace_id = api_workspace
    conn = api_client.app.state.runtime.database.reader
    spans = SpanRepo.list_by_trace(conn, trace_id)
    assert spans
    SpanRepo.update(
        conn,
        spans[0].model_copy(
            update={
                "kind": "tool_call",
                "name": "Read",
                "path_rel": "server/cli.py",
                "waste_category": "re_read",
                "waste_tokens": 40,
            }
        ),
    )
    conn.execute(
        "UPDATE spans SET path_rel = ? WHERE span_id = ?",
        ("/Users/me/secret/abs.py", spans[-1].span_id),
    )
    conn.commit()

    resp = api_client.get("/api/analytics/files?days=365")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ledger"]["distinct_files"] >= 1
    assert body["files"]
    assert all(not item["path_rel"].startswith("/") for item in body["files"])
    assert all(item["estimate_kind"] == "token_share" for item in body["files"])
    assert any(item["path_rel"] == "server/cli.py" for item in body["files"])
    assert all(item["path_rel"] != "/Users/me/secret/abs.py" for item in body["files"])
    assert body["churn"] is not None
    assert any("repo-relative" in note.lower() for note in body["limitations"])


def test_analytics_tools_and_files_tolerate_null_started_at(
    api_client: TestClient,
    api_workspace: tuple[Path, str, str],
) -> None:
    """Real agent logs sometimes omit span timestamps; analytics must not 500."""
    from server.store.repos.spans import SpanRepo

    _root, _workspace_id, trace_id = api_workspace
    conn = api_client.app.state.runtime.database.reader
    spans = SpanRepo.list_by_trace(conn, trace_id)
    assert spans
    SpanRepo.update(
        conn,
        spans[0].model_copy(
            update={
                "kind": "tool_call",
                "name": "Bash",
                "path_rel": "README.md",
                "started_at": None,
                "status": "ok",
            }
        ),
    )
    conn.commit()

    tools = api_client.get("/api/analytics/tools?days=365")
    assert tools.status_code == 200, tools.text
    assert tools.json()["ledger"]["invocations"] >= 1

    files = api_client.get("/api/analytics/files?days=365")
    assert files.status_code == 200, files.text
    assert files.json()["ledger"]["distinct_files"] >= 1


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
    assert body["ledger"]["conclusion"]
    assert "open_count" in body["ledger"]
    assert body["limitations"]
    for row in body["insights"]:
        assert "rank_score" in row
        assert "confidence" in row
        assert "recurrence" in row


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
    body = resp.json()
    assert "experiments" in body
    assert "ledger" in body
    assert "limitations" in body
    ledger = body["ledger"]
    assert set(ledger) >= {
        "conclusion",
        "proposed_count",
        "active_count",
        "portfolio_count",
        "decayed_count",
        "next_action",
        "limitation",
    }


def test_optimize_propose_rejects_apply_true(
    api_client: TestClient, api_workspace: tuple
) -> None:
    root, _ws, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute(
            "UPDATE traces SET peak_context_pct = 90, started_at = ? WHERE trace_id = ?",
            (datetime.now(UTC).isoformat(), trace_id),
        )
    response = api_client.post("/api/actions/optimize_propose", json={"apply": True})
    assert response.status_code == 400
    message = response.json()["error"]["message"].lower()
    assert "experiment_apply" in message


def test_optimize_propose_rejects_llm_true(
    api_client: TestClient, api_workspace: tuple
) -> None:
    root, _ws, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute(
            "UPDATE traces SET peak_context_pct = 90, started_at = ? WHERE trace_id = ?",
            (datetime.now(UTC).isoformat(), trace_id),
        )
    response = api_client.post("/api/actions/optimize_propose", json={"llm": True})
    assert response.status_code == 400
    message = response.json()["error"]["message"].lower()
    assert "reflector" in message


def test_rebuild_view_all_rebuilds_real_views(
    api_client: TestClient, api_workspace: tuple
) -> None:
    response = api_client.post("/api/actions/rebuild_view", json={"view": "all"})
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("job_id"), payload
    body = None
    for _ in range(100):
        job = api_client.get(f"/api/actions/jobs/{payload['job_id']}").json()
        if job.get("status") in {"done", "error", "cancelled", "rejected"}:
            assert job["status"] == "done", job
            body = job["result"]
            break
        time.sleep(0.05)
    assert body is not None, "rebuild_view job did not finish"
    assert body["view"] == "all"
    assert "usage" in body["views"]
    assert "outcomes" in body["views"]
    assert body["traces"] >= 1
    assert body["recomputed"] >= 1


def test_optimize_proposals_create_idempotent_experiment_cards(
    api_client: TestClient, api_workspace: tuple
) -> None:
    root, _ws, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute(
            "UPDATE traces SET peak_context_pct = 90, started_at = ? WHERE trace_id = ?",
            (datetime.now(UTC).isoformat(), trace_id),
        )
    first = api_client.post("/api/actions/optimize_propose", json={})
    second = api_client.post("/api/actions/optimize_propose", json={})
    assert first.status_code == second.status_code == 200
    first_id = first.json()["result"]["proposals"][0]["experiment_id"]
    assert second.json()["result"]["proposals"][0]["experiment_id"] == first_id
    payload = api_client.get("/api/experiments").json()
    experiments = payload["experiments"]
    assert len(experiments) == 1
    assert payload["ledger"]["proposed_count"] == 1
    assert experiments[0] == {
        "experiment_id": first_id,
        "status": "proposed",
        "target_file": "AGENTS.md",
        "created_at": experiments[0]["created_at"],
        "applied_at": None,
        "min_holdout": 8,
        "outcome_n_effective": None,
        "outcome_n_raw": None,
        "sample_size": None,
        "verdict": None,
        "plain_verdict": None,
        "lift_pct": None,
        "effect_ci_low": None,
        "effect_ci_high": None,
        "measured_at": None,
        "last_evaluated_at": None,
        "eval_interval_days": 30,
        "proposal_source": "local",
        "decay_state": "unknown",
        "confound_flag": False,
        "confound_notes": [],
        "effect_history": [],
        "verdict_history": [],
        "regression_outside_interval": False,
        "guard_event_id": None,
        "in_portfolio": False,
    }


def test_search_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/search?q=user")
    assert resp.status_code == 200
    body = resp.json()
    assert body["q"] == "user"
    assert "hits" in body
    assert set(body["facets"]) == {"agent", "outcome", "after", "file", "tool"}
    assert body["search_mode"] == "scan"
    assert "bounded local" in body["search_limitation"]


def test_search_operators_filter_real_fields(api_client: TestClient) -> None:
    by_tool = api_client.get("/api/search", params={"q": "tool:grep"}).json()
    assert by_tool["total"] > 0
    assert all(hit["kind"] == "span" for hit in by_tool["hits"])

    by_source = api_client.get("/api/search", params={"q": "source:claude_code"}).json()
    assert by_source["total"] > 0

    by_error = api_client.get("/api/search", params={"q": "is:error"}).json()
    assert by_error["total"] > 0


def test_sessions_and_search_share_typed_filter_semantics(
    api_client: TestClient, api_workspace: tuple
) -> None:
    root, _workspace_id, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute("UPDATE traces SET cost = 3.5 WHERE trace_id = ?", (trace_id,))
        path = conn.execute(
            "SELECT path_rel FROM spans WHERE trace_id = ? AND path_rel IS NOT NULL LIMIT 1",
            (trace_id,),
        ).fetchone()
        if path is None:
            conn.execute(
                """
                UPDATE spans SET path_rel = 'src/shared-filter.py'
                WHERE span_id = (
                  SELECT span_id FROM spans WHERE trace_id = ? ORDER BY seq LIMIT 1
                )
                """,
                (trace_id,),
            )
            path = ("src/shared-filter.py",)
    assert path is not None
    file_filter = f'file:"{path[0]}"'

    session_cost = api_client.get("/api/traces", params={"q": "cost:>3"}).json()
    search_cost = api_client.get("/api/search", params={"q": "cost:>3"}).json()
    assert trace_id in {row["trace_id"] for row in session_cost["traces"]}
    assert trace_id in {row["trace_id"] for row in search_cost["hits"]}

    session_file = api_client.get("/api/traces", params={"q": file_filter}).json()
    search_file = api_client.get("/api/search", params={"q": file_filter}).json()
    assert trace_id in {row["trace_id"] for row in session_file["traces"]}
    assert trace_id in {row["trace_id"] for row in search_file["hits"]}
    assert session_file["filter_tokens"] == search_file["filter_tokens"]
    assert session_file["filter_errors"] == search_file["filter_errors"] == []


def test_invalid_or_unavailable_filter_is_actionable_and_never_broadens(
    api_client: TestClient,
) -> None:
    for query in ("cost:many", "claim:unsupported", '"unterminated'):
        sessions = api_client.get("/api/traces", params={"q": query}).json()
        search = api_client.get("/api/search", params={"q": query}).json()
        assert sessions["traces"] == []
        assert search["hits"] == []
        assert sessions["filter_errors"] == search["filter_errors"]
        assert sessions["filter_errors"][0]["message"]


def test_search_counts_matches_but_materializes_only_the_bounded_page(
    api_client: TestClient,
) -> None:
    response = api_client.get(
        "/api/search",
        params={"q": "source:claude_code", "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["hits"]) == 1
    assert body["total"] > len(body["hits"])


def test_trace_sort_options_are_stable_and_url_contract_is_bounded(api_client: TestClient) -> None:
    for sort, field in (
        ("cost", "cost"),
        ("waste", "waste_tokens"),
        ("tokens", None),
        ("duration", None),
        ("quality", None),
    ):
        response = api_client.get("/api/traces", params={"sort": sort, "limit": 50})
        assert response.status_code == 200
        rows = response.json()["traces"]
        if field is not None:
            values = [row[field] for row in rows]
            assert values == sorted(values, reverse=True)


def test_workspace_shape(api_client: TestClient, api_workspace: tuple) -> None:
    root, ws_id, _trace_id = api_workspace
    resp = api_client.get("/api/workspace")
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspace_id"] == ws_id
    assert body["root_path"] == str(root)
    assert "adapters" in body
    assert body["health"]["trace_count"] >= 1
    assert body["adapters"][0]["parse_coverage"] == 1.0
    assert body["health"]["adapter_warnings"] == []


def test_workspace_warns_when_adapter_format_may_have_changed(
    api_client: TestClient, api_workspace: tuple
) -> None:
    root, ws_id, _trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.execute(
            """UPDATE adapter_parse_health
               SET fully_parsed = 0, degraded = 1,
                   recent_unknown_fields_json = '{"future_field": 8}'
               WHERE workspace_id = ? AND adapter_id = 'claude_code'""",
            (ws_id,),
        )
    body = api_client.get("/api/workspace").json()
    warning = body["health"]["adapter_warnings"][0]
    assert warning["adapter_id"] == "claude_code"
    assert "numbers may be incomplete" in warning["message"]
    assert "github.com/Harsh-Daga/Cairn/issues/new" in warning["issue_url"]


def test_actions_manifest_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/actions")
    assert resp.status_code == 200
    body = resp.json()
    names = {item["name"] for item in body["actions"]}
    assert "sync" in names
    assert "check" in names
    assert "demo_seed" in names
    assert "reflector_preview" in names
    assert "reflector_run" in names
    assert len(names) == 48
    assert "regression_run" in names
    assert "regression_compare" in names
    assert "db_backup_list" in names


def test_reflector_action_requires_unchanged_preview_consent(
    api_client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-private")
    preview_response = api_client.post(
        "/api/actions/reflector_preview",
        json={"backend": "provider:openai", "days": 14},
    )
    assert preview_response.status_code == 200
    preview_result = preview_response.json()["result"]
    preview = preview_result["preview"]
    assert preview["destination_origin"] == "https://api.openai.com"
    assert "sk-private" not in json.dumps(preview)
    assert preview_result["network_attempted"] is False

    denied = api_client.post(
        "/api/actions/reflector_run",
        json={
            "backend": "provider:openai",
            "days": 14,
            "consent_token": "0" * 64,
        },
    )
    assert denied.status_code == 200
    denied_result = denied.json()["result"]
    assert denied_result["network_attempted"] is False
    assert denied_result["error"]["code"] == "consent_mismatch"

    response = httpx.Response(
        200,
        json={"choices": [{"message": {"content": '{"proposals":[]}'}}]},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    calls: list[str] = []

    def approved_post(url: str, **_kwargs):
        calls.append(url)
        return response

    monkeypatch.setattr("server.improve.reflector.httpx.post", approved_post)
    approved = api_client.post(
        "/api/actions/reflector_run",
        json={
            "backend": "provider:openai",
            "days": 14,
            "consent_token": preview["consent_token"],
        },
    )
    assert approved.status_code == 200
    approved_result = approved.json()["result"]
    assert approved_result["network_attempted"] is True
    assert approved_result["proposals"] == []
    assert calls == ["https://api.openai.com/v1/chat/completions"]


def test_action_check_runs(api_client: TestClient) -> None:
    resp = api_client.post("/api/actions/check", json={})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_session_scrubbed_export_is_workspace_scoped_and_includes_evidence(
    api_client: TestClient,
    api_workspace: tuple[Path, str, str],
) -> None:
    _root, _workspace_id, trace_id = api_workspace
    response = api_client.post(
        "/api/actions/export_bundle",
        json={"trace_id": trace_id, "scrub": True},
    )
    assert response.status_code == 200
    result = response.json()["result"]
    payload = json.loads(Path(result["path"]).read_text())
    assert payload["schema_version"] == 1
    assert payload["scrubbed"] is True
    assert payload["traces"][0]["trace_id"] == trace_id
    assert payload["traces"][0]["title"] == "<redacted>"
    assert payload["spans"]
    assert all(span["text_inline"] in {None, "<redacted>"} for span in payload["spans"])
    assert "normalized spans" in result["included_field_classes"]

    missing = api_client.post(
        "/api/actions/export_bundle",
        json={"trace_id": "not-in-this-workspace", "scrub": True},
    )
    assert missing.status_code == 200
    assert missing.json()["result"]["count"] == 0


def test_openapi_validates(api_client: TestClient) -> None:
    resp = api_client.get("/api/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "Cairn"
    assert "/api/overview" in schema["paths"]
    assert "/api/traces" in schema["paths"]
    assert "/api/actions/{name}" in schema["paths"]
    operations = [
        operation["operationId"]
        for methods in schema["paths"].values()
        for operation in methods.values()
    ]
    assert len(operations) == len(set(operations))
    assert all("_api_" not in operation_id for operation_id in operations)
