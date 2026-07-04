"""Episodic memory — Phase M."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from cairn.ledger.ledger import new_run_id


def _task_signature(events: list[dict[str, Any]]) -> str:
    prompts = [
        str(e.get("text_inline") or "")[:200] for e in events if e.get("type") == "user_prompt"
    ]
    base = prompts[0] if prompts else ""
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def _winning_approach(events: list[dict[str, Any]]) -> dict[str, Any]:
    paths: list[str] = []
    for e in events:
        if e.get("type") == "tool_call" and e.get("path_rel"):
            paths.append(str(e["path_rel"]))
    edits = sum(1 for e in events if e.get("tool_norm_name") == "edit")
    return {"files_order": paths[:20], "edit_count": edits}


def maybe_capture_episode(
    writer: Any,
    run_id: str,
    *,
    events: list[dict[str, Any]] | None = None,
) -> None:
    """When a session succeeds on a task that historically cascaded, store episode."""
    conn: sqlite3.Connection = writer.connection
    if events is None:
        events = writer.load_events(run_id)
    diag = conn.execute(
        "SELECT outcome_label FROM diagnostics WHERE run_id = ?", (run_id,)
    ).fetchone()
    out = conn.execute(
        "SELECT outcome_label, commit_landed FROM outcomes WHERE run_id = ?", (run_id,)
    ).fetchone()
    label = (diag["outcome_label"] if diag else None) or (out["outcome_label"] if out else None)
    if label != "landed" and not (out and out["commit_landed"]):
        return

    sig = _task_signature(events)
    prior_cascade = conn.execute(
        """
        SELECT COUNT(*) AS n FROM diagnostics d
        JOIN runs r ON r.run_id = d.run_id
        WHERE d.primary_category IS NOT NULL
          AND d.outcome_label NOT IN ('landed')
          AND d.run_id != ?
        """,
        (run_id,),
    ).fetchone()
    if not prior_cascade or int(prior_cascade["n"]) < 1:
        return

    approach = _winning_approach(events)
    episode_id = new_run_id()
    conn.execute(
        """
        INSERT OR IGNORE INTO episodes (
            episode_id, run_id, task_signature, approach_json, outcome_label, captured_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            episode_id,
            run_id,
            sig,
            json.dumps(approach),
            label or "landed",
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()


def recall_episode(conn: sqlite3.Connection, task: str) -> dict[str, Any] | None:
    sig = hashlib.sha256(task.encode()).hexdigest()[:16]
    row = conn.execute(
        """
        SELECT episode_id, run_id, approach_json, outcome_label, captured_at
        FROM episodes WHERE task_signature = ?
        ORDER BY captured_at DESC LIMIT 1
        """,
        (sig,),
    ).fetchone()
    if row is None:
        # fuzzy: prefix match on any episode
        row = conn.execute(
            "SELECT episode_id, run_id, approach_json, outcome_label, captured_at "
            "FROM episodes ORDER BY captured_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    try:
        approach = json.loads(row["approach_json"])
    except json.JSONDecodeError:
        approach = {}
    return {
        "episode_id": row["episode_id"],
        "run_id": row["run_id"],
        "approach": approach,
        "outcome_label": row["outcome_label"],
        "captured_at": row["captured_at"],
    }
