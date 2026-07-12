"""Deterministic demo data seeding for Cairn."""

from __future__ import annotations

import json
import sqlite3
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from server.store.migrate import migrate

DEMO_TRACE_COUNT = 120
DEMO_DAYS = 30
DEMO_SOURCES = ("claude_code", "cursor", "codex", "cline")
DEMO_ACTORS = (
    ("human", "Harsh"),
    ("agent", "Cairn Bot"),
    ("service", "CI Runner"),
)
DEMO_ROOT = Path("~/.cairn-demo").expanduser()
DEMO_WORKSPACE_ID = str(uuid5(NAMESPACE_URL, "cairn-demo/workspace"))
DEMO_FAILURE_TRACE_INDEX = 73
DEMO_MULTI_AGENT_TRACE_INDEX = 42
DEMO_TAIL_TRACE_INDEX = 117


@dataclass(frozen=True)
class DemoSeedResult:
    root: Path
    workspace_id: str
    trace_count: int
    actor_count: int
    source_count: int
    reset: bool


def _det_uuid(label: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"cairn-demo/{label}"))


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
        start_day = (now - timedelta(days=DEMO_DAYS - 1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )

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

        for idx in range(DEMO_TRACE_COUNT):
            day_offset = idx // 4
            slot = idx % 4
            trace_started = start_day + timedelta(days=day_offset, hours=slot * 2)
            duration_min = 8 + (idx % 9) * 4
            trace_ended = trace_started + timedelta(minutes=duration_min)

            source = DEMO_SOURCES[idx % len(DEMO_SOURCES)]
            actor_id = actor_ids[idx % len(actor_ids)]
            model = "claude-4.6-sonnet" if idx < 80 else "gpt-5.5-medium"
            project = "demo-app" if idx % 2 == 0 else "ops-tooling"
            trace_id = str(uuid5(NAMESPACE_URL, f"cairn-demo/trace/{idx:03d}"))
            status = "error" if idx == DEMO_FAILURE_TRACE_INDEX else "completed"
            base_input = 1200 + (idx % 11) * 130
            base_output = 700 + (idx % 7) * 90
            waste = 120 + (idx % 6) * 45
            cost = round((base_input + base_output) * 0.000003, 4)
            if idx == DEMO_TAIL_TRACE_INDEX:
                cost = 14.75
                waste = 3100
            title = (
                "Failure cascade after bad migration"
                if idx == DEMO_FAILURE_TRACE_INDEX
                else f"Demo trace {idx + 1:03d} — {source}"
            )

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
                    "v4/phase-l7-demo",
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
                    "ReadFile",
                    "agent-main",
                    "main",
                    (trace_started + timedelta(minutes=3)).isoformat(),
                    (trace_started + timedelta(minutes=5)).isoformat(),
                    110000,
                    "error" if idx == DEMO_FAILURE_TRACE_INDEX else "ok",
                    None,
                    220,
                    30,
                    0,
                    0,
                    38,
                    "Read file and inspect context",
                    _det_uuid(f"{trace_id}/text/tool"),
                    _det_uuid(f"{trace_id}/args/tool"),
                    "server/cli.py",
                    "re_read" if idx % 8 == 0 else None,
                    80 if idx % 8 == 0 else 0,
                    json.dumps({"tool_name": "ReadFile"}),
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

        evidence_rows = [
            (
                "demo-evidence-reread",
                "detector:reread-hotspot@2",
                json.dumps(
                    [
                        str(uuid5(NAMESPACE_URL, "cairn-demo/trace/008")),
                        str(uuid5(NAMESPACE_URL, "cairn-demo/trace/016")),
                    ]
                ),
                json.dumps({"waste_tokens": 2840, "confidence": 0.91}),
            ),
            (
                "demo-evidence-tail",
                "detector:tail-cost@1",
                json.dumps(
                    [str(uuid5(NAMESPACE_URL, f"cairn-demo/trace/{DEMO_TAIL_TRACE_INDEX:03d}"))]
                ),
                json.dumps({"expected_worst_cost": 16.2, "threshold": 2.9}),
            ),
        ]
        for evidence_id, producer, trace_ids_json, metrics_json in evidence_rows:
            conn.execute(
                """
                INSERT INTO evidence (
                  evidence_id, producer, produced_at, trace_ids_json, span_ids_json, metrics_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (evidence_id, producer, now.isoformat(), trace_ids_json, "[]", metrics_json),
            )

        insight_rows = [
            (
                "demo-insight-reread",
                "demo:reread-hotspot",
                "reread_hotspot",
                "warning",
                "Repeated file reads are rebilling context",
                "Multiple sessions repeatedly re-read the same files before editing.",
                "demo-evidence-reread",
                4.75,
                "optimize_propose",
                "new",
            ),
            (
                "demo-insight-tail",
                "demo:tail-outlier",
                "tail_outlier",
                "error",
                "One session dominates tail risk",
                "A single outlier session creates a disproportionate expected worst-case cost.",
                "demo-evidence-tail",
                9.2,
                "check",
                "ack",
            ),
        ]
        for (
            insight_id,
            fingerprint,
            detector,
            severity,
            title,
            body,
            evidence_id,
            savings_estimate,
            action,
            state,
        ) in insight_rows:
            conn.execute(
                """
                INSERT INTO insights (
                  insight_id, fingerprint, detector, detector_version, severity, title, body,
                  evidence_id, savings_estimate, savings_ci_json, action, created_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    insight_id,
                    fingerprint,
                    detector,
                    1,
                    severity,
                    title,
                    body,
                    evidence_id,
                    savings_estimate,
                    json.dumps({"low": savings_estimate * 0.6, "high": savings_estimate * 1.2}),
                    action,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            conn.execute(
                """
                INSERT INTO insight_states (insight_id, state, changed_at, changed_by)
                VALUES (?, ?, ?, ?)
                """,
                (insight_id, state, now.isoformat(), "demo-seed"),
            )

        conn.execute(
            """
            INSERT INTO experiments (
              experiment_id, created_at, target_file, block_key, kind, content, evidence_id, status,
              applied_at, min_holdout, baseline_metric, baseline_n_effective, outcome_metric,
              outcome_n_effective, effect_estimate, effect_ci_low, effect_ci_high, test_method,
              verdict, confound_flag, measured_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "demo-exp-verdict-001",
                now.isoformat(),
                "AGENTS.md",
                "reread-policy",
                "append",
                "- Avoid rereading full files unless content changed.\n",
                "demo-evidence-reread",
                "verdict",
                (now - timedelta(days=10)).isoformat(),
                8,
                0.34,
                12.0,
                0.21,
                15.0,
                -0.13,
                -0.2,
                -0.05,
                "diff-in-diff",
                "win",
                0,
                (now - timedelta(days=1)).isoformat(),
            ),
        )

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
