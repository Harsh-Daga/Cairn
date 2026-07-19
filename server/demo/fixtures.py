"""SQLite fixture orchestration for the deterministic demo scenarios."""

from __future__ import annotations

import json
import sqlite3
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from server.demo.guard_fixtures import seed_guard_fixtures
from server.demo.improvement_fixtures import seed_improvement_fixtures
from server.demo.scenarios import (
    DEMO_ACTORS,
    DEMO_DAYS,
    DEMO_FAILURE_TRACE_INDEX,
    DEMO_MULTI_AGENT_TRACE_INDEX,
    DEMO_ROOT,
    DEMO_SOURCES,
    DEMO_TAIL_TRACE_INDEX,
    DEMO_TRACE_COUNT,
    DEMO_WORKSPACE_ID,
    DemoSeedResult,
    deterministic_uuid,
    trace_scenarios,
)
from server.store.migrate import migrate

__all__ = [
    "DEMO_ACTORS",
    "DEMO_DAYS",
    "DEMO_FAILURE_TRACE_INDEX",
    "DEMO_MULTI_AGENT_TRACE_INDEX",
    "DEMO_ROOT",
    "DEMO_SOURCES",
    "DEMO_TAIL_TRACE_INDEX",
    "DEMO_TRACE_COUNT",
    "DEMO_WORKSPACE_ID",
    "DemoSeedResult",
    "seed_demo_workspace",
]


def _det_uuid(label: str) -> str:
    return deterministic_uuid(label)


def _demo_tool_name(idx: int) -> str:
    rotation = ("Read", "Bash", "Edit", "Grep", "mcp:docs/search", "custom_probe")
    return rotation[idx % len(rotation)]


def _demo_tool_detail(idx: int) -> str:
    name = _demo_tool_name(idx)
    if name.startswith("mcp:"):
        return f"Call {name} for reference material"
    if name == "Bash":
        return "Run a bounded local command"
    if name == "Edit":
        return "Apply a focused file edit"
    if name == "Grep":
        return "Search the workspace for symbols"
    if name == "custom_probe":
        return "Invoke an unmapped custom tool"
    return "Read file and inspect context"


def _demo_tool_waste(idx: int) -> str | None:
    if idx % 8 == 0:
        return "re_read"
    if idx % 11 == 0:
        return "retry_loop"
    return None


def _demo_tool_path(idx: int) -> str:
    rotation = (
        "server/cli.py",
        "server/app.py",
        "ui/src/app.tsx",
        "tests/test_demo.py",
        "docs/README.md",
        "package.json",
    )
    return rotation[idx % len(rotation)]


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    migrate(conn)
    return conn


def _clear_workspace(conn: sqlite3.Connection, workspace_id: str) -> None:
    trace_ids = [
        str(row["trace_id"])
        for row in conn.execute(
            "SELECT trace_id FROM traces WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchall()
    ]
    if trace_ids:
        placeholders = ",".join("?" for _ in trace_ids)
        span_ids_subquery = f"SELECT span_id FROM spans WHERE trace_id IN ({placeholders})"
        conn.execute(f"DELETE FROM outcomes WHERE trace_id IN ({placeholders})", trace_ids)
        conn.execute(f"DELETE FROM diagnostics WHERE trace_id IN ({placeholders})", trace_ids)
        conn.execute(f"DELETE FROM fingerprints WHERE trace_id IN ({placeholders})", trace_ids)
        conn.execute(f"DELETE FROM data_quality WHERE trace_id IN ({placeholders})", trace_ids)
        conn.execute(
            f"DELETE FROM span_links WHERE from_span_id IN ({span_ids_subquery})",
            trace_ids,
        )
        conn.execute(
            f"DELETE FROM span_links WHERE to_span_id IN ({span_ids_subquery})",
            trace_ids,
        )
        conn.execute(
            f"DELETE FROM context_regions WHERE span_id IN ({span_ids_subquery})",
            trace_ids,
        )
        conn.execute(f"DELETE FROM spans WHERE trace_id IN ({placeholders})", trace_ids)
        with suppress(sqlite3.OperationalError):
            conn.execute(f"DELETE FROM spans_fts WHERE trace_id IN ({placeholders})", trace_ids)
        conn.execute(f"DELETE FROM traces WHERE trace_id IN ({placeholders})", trace_ids)
    conn.execute("DELETE FROM rollup_daily WHERE workspace_id = ?", (workspace_id,))
    conn.execute(
        "DELETE FROM ingest_cursors WHERE source IN (?, ?, ?, ?)",
        DEMO_SOURCES,
    )
    conn.execute("""
        DELETE FROM insight_states
        WHERE insight_id IN (
            SELECT insight_id FROM insights WHERE fingerprint LIKE 'demo:%'
        )
    """)
    conn.execute("DELETE FROM insights WHERE fingerprint LIKE 'demo:%'")
    conn.execute("DELETE FROM experiments WHERE experiment_id LIKE 'demo-%'")
    conn.execute("DELETE FROM evidence WHERE evidence_id LIKE 'demo-%'")
    conn.execute("DELETE FROM workspaces WHERE workspace_id = ?", (workspace_id,))
    conn.execute("DELETE FROM actors WHERE actor_id LIKE 'demo-%'")


def seed_demo_workspace(root: Path | None = None, *, reset: bool = False) -> DemoSeedResult:
    """Seed a deterministic workspace with realistic Cairn demo data."""
    target_root = (root or DEMO_ROOT).expanduser().resolve()
    db_path = target_root / ".cairn" / "cairn.db"
    if reset and db_path.exists():
        db_path.unlink()
    target_root.mkdir(parents=True, exist_ok=True)

    conn = _connect(db_path)
    try:
        _clear_workspace(conn, DEMO_WORKSPACE_ID)

        now = datetime.now(UTC)
        conn.execute(
            """
            INSERT INTO workspaces (workspace_id, root_path, name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (DEMO_WORKSPACE_ID, str(target_root), "cairn-demo", now.isoformat()),
        )

        actor_ids: list[str] = []
        for kind, display_name in DEMO_ACTORS:
            actor_id = f"demo-{_det_uuid(f'actor:{kind}:{display_name}')}"
            actor_ids.append(actor_id)
            conn.execute(
                """
                INSERT INTO actors (actor_id, kind, display_name, identity_hint)
                VALUES (?, ?, ?, ?)
                """,
                (actor_id, kind, display_name, f"{kind}@demo.local"),
            )

        rollups: dict[tuple[str, str, str, str], dict[str, float]] = {}

        for scenario in trace_scenarios(now):
            idx = scenario.index
            trace_started = scenario.started_at
            trace_ended = scenario.ended_at
            source = scenario.source
            actor_id = actor_ids[scenario.actor_index]
            model = scenario.model
            project = scenario.project
            trace_id = scenario.trace_id
            status = scenario.status
            base_input = scenario.input_tokens
            base_output = scenario.output_tokens
            waste = scenario.waste_tokens
            cost = scenario.cost
            title = scenario.title

            conn.execute(
                """
                INSERT INTO traces (
                  trace_id, workspace_id, source, external_id, actor_id, project, cwd, model,
                  git_branch, git_commit, started_at, ended_at, status, title,
                  input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
                  reasoning_tokens, cost, cost_source, context_window, peak_context_pct,
                  span_count, tool_calls, tool_errors, waste_tokens, difficulty, difficulty_bucket
                )
                VALUES (
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    trace_id,
                    DEMO_WORKSPACE_ID,
                    source,
                    f"demo-session-{idx:03d}",
                    actor_id,
                    project,
                    str(target_root),
                    model,
                    "demo/reference",
                    f"deadbeef{idx:02x}",
                    trace_started.isoformat(),
                    trace_ended.isoformat(),
                    status,
                    title,
                    base_input,
                    base_output,
                    80 + (idx % 5) * 20,
                    40 + (idx % 4) * 12,
                    20 + (idx % 3) * 9,
                    cost,
                    "measured",
                    128000,
                    round(38 + (idx % 9) * 5.2, 2),
                    4 if idx == DEMO_MULTI_AGENT_TRACE_INDEX else 3,
                    1 if idx % 3 else 2,
                    1 if idx == DEMO_FAILURE_TRACE_INDEX else 0,
                    waste,
                    round(0.25 + (idx % 10) * 0.07, 3),
                    "high" if idx % 4 == 0 else "medium",
                ),
            )

            root_span_id = str(uuid5(NAMESPACE_URL, f"{trace_id}/span/root"))
            user_span_id = str(uuid5(NAMESPACE_URL, f"{trace_id}/span/user"))
            tool_span_id = str(uuid5(NAMESPACE_URL, f"{trace_id}/span/tool"))
            sub_span_id = str(uuid5(NAMESPACE_URL, f"{trace_id}/span/sub"))
            span_rows = [
                (
                    root_span_id,
                    trace_id,
                    None,
                    1,
                    "agent",
                    "planner",
                    "agent-main",
                    "main",
                    trace_started.isoformat(),
                    (trace_started + timedelta(minutes=2)).isoformat(),
                    120000,
                    "ok",
                    model,
                    320,
                    90,
                    0,
                    0,
                    20,
                    "Planning steps",
                    _det_uuid(f"{trace_id}/text/root"),
                    None,
                    "README.md",
                    None,
                    0,
                    json.dumps({"phase": "plan"}),
                ),
                (
                    user_span_id,
                    trace_id,
                    root_span_id,
                    2,
                    "user_msg",
                    "user prompt",
                    "human",
                    "main",
                    (trace_started + timedelta(minutes=2)).isoformat(),
                    (trace_started + timedelta(minutes=3)).isoformat(),
                    60000,
                    "ok",
                    None,
                    140,
                    0,
                    0,
                    0,
                    26,
                    "Need a robust fix with tests",
                    _det_uuid(f"{trace_id}/text/user"),
                    None,
                    None,
                    None,
                    0,
                    json.dumps({"intent": "feature"}),
                ),
                (
                    tool_span_id,
                    trace_id,
                    root_span_id,
                    3,
                    "tool_call",
                    _demo_tool_name(idx),
                    "agent-main",
                    "main",
                    (trace_started + timedelta(minutes=3)).isoformat(),
                    (trace_started + timedelta(minutes=5)).isoformat(),
                    40_000 + (idx % 17) * 7_000,
                    "error" if idx == DEMO_FAILURE_TRACE_INDEX else "ok",
                    None,
                    220,
                    30 + (idx % 5) * 12,
                    0,
                    0,
                    38,
                    _demo_tool_detail(idx),
                    _det_uuid(f"{trace_id}/text/tool"),
                    _det_uuid(f"{trace_id}/args/tool"),
                    _demo_tool_path(idx),
                    _demo_tool_waste(idx),
                    80 if idx % 8 == 0 else (40 if idx % 11 == 0 else 0),
                    json.dumps({"tool_name": _demo_tool_name(idx)}),
                ),
            ]
            if idx == DEMO_MULTI_AGENT_TRACE_INDEX:
                span_rows.append(
                    (
                        sub_span_id,
                        trace_id,
                        tool_span_id,
                        4,
                        "subagent",
                        "specialist",
                        "agent-reviewer",
                        "lane-b",
                        (trace_started + timedelta(minutes=5)).isoformat(),
                        (trace_started + timedelta(minutes=7)).isoformat(),
                        90000,
                        "ok",
                        model,
                        180,
                        55,
                        0,
                        0,
                        42,
                        "Subagent verifies edge cases",
                        _det_uuid(f"{trace_id}/text/sub"),
                        None,
                        "tests/test_demo.py",
                        None,
                        0,
                        json.dumps({"role": "review"}),
                    )
                )

            conn.executemany(
                """
                INSERT INTO spans (
                  span_id, trace_id, parent_span_id, seq, kind, name, agent_id, agent_lane,
                  started_at, ended_at, duration_ms, status, model, input_tokens, output_tokens,
                  cache_read_tokens, cache_creation_tokens, context_tokens_after, text_inline,
                  text_hash, args_hash, path_rel, waste_category, waste_tokens, attrs_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                span_rows,
            )

            if idx == DEMO_MULTI_AGENT_TRACE_INDEX:
                conn.execute(
                    """
                    INSERT INTO span_links (from_span_id, to_span_id, link_type)
                    VALUES (?, ?, 'handoff')
                    """,
                    (tool_span_id, sub_span_id),
                )
            if idx == DEMO_FAILURE_TRACE_INDEX:
                conn.execute(
                    """
                    INSERT INTO diagnostics (
                      trace_id, failure_origin_span_id, failure_signature, primary_category,
                      secondary_category, cascade_root_span_id, cascade_blast_tokens,
                      ideal_path_savings_tokens, computed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace_id,
                        tool_span_id,
                        "sqlite.OperationalError:no such table",
                        "schema",
                        "migration",
                        root_span_id,
                        2400,
                        1600,
                        now.isoformat(),
                    ),
                )

            for region, tokens in (("system", 120), ("tool_result", 420), ("history", 260)):
                conn.execute(
                    """
                    INSERT INTO context_regions (
                      span_id, region, tokens, cost, content_hash,
                      first_turn, last_seen_turn, still_in_window
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tool_span_id,
                        region,
                        tokens,
                        round(tokens * 0.0000009, 6),
                        _det_uuid(f"{trace_id}/region/{region}"),
                        1,
                        3,
                        1,
                    ),
                )

            vector = [
                round(0.18 + (idx % 6) * 0.05, 3),
                round(0.22 + (idx % 5) * 0.04, 3),
                round(0.11 + (idx % 4) * 0.06, 3),
                round(0.16 + (idx % 7) * 0.03, 3),
                round(0.28 + (idx % 3) * 0.08, 3),
            ]
            if idx >= 100:
                vector = [round(v * 1.5, 3) for v in vector]
            conn.execute(
                """
                INSERT INTO fingerprints (
                  trace_id, project, model, source, week, ts, vector_json,
                  read_write_ratio, exploration_ratio, retry_rate, tool_entropy,
                  turn_count, context_fill_traj_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    project,
                    model,
                    source,
                    trace_started.strftime("%Y-W%U"),
                    trace_started.isoformat(),
                    json.dumps(vector),
                    vector[0],
                    vector[1],
                    vector[2],
                    vector[3],
                    3 + (1 if idx == DEMO_MULTI_AGENT_TRACE_INDEX else 0),
                    json.dumps([22, 35, 41]),
                ),
            )

            conn.execute(
                """
                INSERT INTO outcomes (
                  trace_id, commit_sha, commit_landed, files_changed_json, tests_run, tests_passed,
                  tests_failed, build_status, quality_score, cost_per_success, outcome_label,
                  label_source, captured_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    f"{idx:040x}"[-40:],
                    0 if idx == DEMO_FAILURE_TRACE_INDEX else 1,
                    json.dumps(["server/cli.py", "tests/test_demo.py"]),
                    18,
                    15 if idx == DEMO_FAILURE_TRACE_INDEX else 18,
                    3 if idx == DEMO_FAILURE_TRACE_INDEX else 0,
                    "failed" if idx == DEMO_FAILURE_TRACE_INDEX else "passed",
                    round(0.46 + (idx % 9) * 0.055, 3),
                    round(cost / max(0.3, 0.65 + (idx % 5) * 0.07), 4),
                    "failure" if idx == DEMO_FAILURE_TRACE_INDEX else "success",
                    "demo-seed",
                    now.isoformat(),
                ),
            )

            conn.execute(
                """
                INSERT INTO data_quality (
                  trace_id, pct_tokens_measured, pct_tokens_estimated,
                  timestamps_present, cost_source,
                  parser_version, dropped_events, notes_json, computed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    0.98,
                    0.02,
                    1,
                    "measured",
                    "demo-seed-v1",
                    0,
                    json.dumps({}),
                    now.isoformat(),
                ),
            )

            day = trace_started.date().isoformat()
            key = (day, project, source, model)
            bucket = rollups.setdefault(
                key,
                {
                    "traces": 0.0,
                    "tool_calls": 0.0,
                    "tool_errors": 0.0,
                    "input_tokens": 0.0,
                    "output_tokens": 0.0,
                    "cache_read_tokens": 0.0,
                    "cache_creation_tokens": 0.0,
                    "cost": 0.0,
                    "waste_tokens": 0.0,
                },
            )
            bucket["traces"] += 1
            bucket["tool_calls"] += 2 if idx % 3 == 0 else 1
            bucket["tool_errors"] += 1 if idx == DEMO_FAILURE_TRACE_INDEX else 0
            bucket["input_tokens"] += base_input
            bucket["output_tokens"] += base_output
            bucket["cache_read_tokens"] += 80 + (idx % 5) * 20
            bucket["cache_creation_tokens"] += 40 + (idx % 4) * 12
            bucket["cost"] += cost
            bucket["waste_tokens"] += waste

            with suppress(sqlite3.OperationalError):
                conn.execute(
                    """
                    INSERT INTO spans_fts (trace_id, span_id, text_inline)
                    VALUES (?, ?, ?)
                    """,
                    (
                        trace_id,
                        tool_span_id,
                        "Read file and inspect context",
                    ),
                )

        for (day, project, source, model), row in rollups.items():
            conn.execute(
                """
                INSERT INTO rollup_daily (
                  day, workspace_id, project, source, model, traces, tool_calls, tool_errors,
                  input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
                  cost, waste_tokens
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    day,
                    DEMO_WORKSPACE_ID,
                    project,
                    source,
                    model,
                    int(row["traces"]),
                    int(row["tool_calls"]),
                    int(row["tool_errors"]),
                    int(row["input_tokens"]),
                    int(row["output_tokens"]),
                    int(row["cache_read_tokens"]),
                    int(row["cache_creation_tokens"]),
                    round(row["cost"], 4),
                    int(row["waste_tokens"]),
                ),
            )

        for source in DEMO_SOURCES:
            conn.execute(
                """
                INSERT INTO ingest_cursors (source, stream, cursor_json, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    source,
                    f"{source}:main",
                    json.dumps({"offset": DEMO_TRACE_COUNT // len(DEMO_SOURCES)}),
                    now.isoformat(),
                ),
            )

        seed_improvement_fixtures(conn, now=now)
        seed_guard_fixtures(conn, now=now)

        conn.commit()
    finally:
        conn.close()

    return DemoSeedResult(
        root=target_root,
        workspace_id=DEMO_WORKSPACE_ID,
        trace_count=DEMO_TRACE_COUNT,
        actor_count=len(DEMO_ACTORS),
        source_count=len(DEMO_SOURCES),
        reset=reset,
    )
