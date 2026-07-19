"""Deterministic evidence, insight, and experiment fixtures for the demo."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from server.demo.scenarios import DEMO_TAIL_TRACE_INDEX


def seed_improvement_fixtures(conn: sqlite3.Connection, *, now: datetime) -> None:
    """Insert the demo's stable evidence-to-verdict improvement journey."""
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
          verdict, confound_flag, measured_at, proposal_source, decay_state, last_evaluated_at,
          plain_verdict, confound_notes_json, effect_history_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            "difference_in_means+anytime_valid_cs",
            "improved",
            0,
            (now - timedelta(days=1)).isoformat(),
            "local",
            "healthy",
            (now - timedelta(days=1)).isoformat(),
            "Holdout evidence suggests this rule improved the metric by about 13%.",
            "[]",
            "[-0.11,-0.13]",
        ),
    )
