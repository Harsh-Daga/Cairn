"""Build session detail payload for /api/session/{id}."""

from __future__ import annotations

import sqlite3
from typing import Any


def session_payload(conn: sqlite3.Connection, *, run_id: str) -> dict[str, Any]:
    run_row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run_row is None:
        return {"error": "not_found"}

    events = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY seq", (run_id,)
        ).fetchall()
    ]

    turns = _build_turns(events)
    for turn in turns:
        for event in turn["events"]:
            event["_turn_n"] = turn["turn_number"]

    waste_events = [e for e in events if e.get("waste_category")]
    files = _files_touched(events)
    graph = build_session_graph(events, turns)
    fingerprint = _fingerprint_section(conn, run_row, events)

    run = dict(run_row)
    run["has_cost"] = bool(run.get("has_cost"))

    diag_row = conn.execute("SELECT * FROM diagnostics WHERE run_id = ?", (run_id,)).fetchone()
    diagnostics = dict(diag_row) if diag_row else None
    dq_row = conn.execute(
        "SELECT pct_tokens_measured, cost_source, notes_json FROM data_quality WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    confidence = _session_confidence(dq_row, run)
    from cairn.metrics.normalized import cost_vs_expected
    from cairn.render.narrative import session_narrative

    normalized = cost_vs_expected(conn, run)
    narrative = session_narrative(diagnostics or {}, normalized) if diagnostics else None

    ideal_path: dict[str, Any] | None = None
    if diagnostics:
        from cairn.diagnose.ideal import ideal_path_savings

        _, ideal_path = ideal_path_savings(events)

    rewind_suggestion = _rewind_suggestion(run, diagnostics, events)
    agents = _agents_section(run, events)

    event_count = len(events)

    return {
        "run": run,
        "turns": turns,
        "waste_events": waste_events,
        "files": files,
        "graph": graph,
        "fingerprint": fingerprint,
        "diagnostics": diagnostics,
        "normalized": normalized,
        "confidence": confidence,
        "narrative": narrative,
        "ideal_path": ideal_path,
        "rewind_suggestion": rewind_suggestion,
        "agents": agents,
        "diagnosis_available": diagnostics is not None,
        "event_count_for_diagnosis": event_count,
        "failure_origin_event_id": diagnostics.get("failure_origin_event_id")
        if diagnostics
        else None,
        "cascade_root_event_id": diagnostics.get("cascade_root_event_id") if diagnostics else None,
    }


def _agents_section(
    run: dict[str, Any], events: list[dict[str, Any]]
) -> list[dict[str, Any]] | None:
    """Per-agent token/cost rollup when lineage is present on events."""
    if not any(e.get("agent_lane") for e in events):
        return None
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        lane = event.get("agent_lane")
        if not lane:
            continue
        agent_id = str(event.get("agent_id") or "unknown")
        key = (agent_id, str(lane))
        group = groups.setdefault(
            key,
            {
                "agent_id": agent_id,
                "agent_lane": str(lane),
                "events": 0,
                "tokens": 0,
                "cost_estimate": None,
            },
        )
        group["events"] += 1
        group["tokens"] += int(event.get("input_tokens") or 0) + int(
            event.get("output_tokens") or 0
        )

    agents = list(groups.values())
    total_tokens = sum(int(a["tokens"]) for a in agents)
    run_cost = float(run.get("total_cost") or 0)
    if bool(run.get("has_cost")) and total_tokens > 0 and run_cost > 0:
        for agent in agents:
            share = int(agent["tokens"]) / total_tokens
            agent["cost_estimate"] = round(run_cost * share, 6)
            agent["cost_method"] = "apportioned"
    return agents


def _rewind_suggestion(
    run: dict[str, Any],
    diagnostics: dict[str, Any] | None,
    events: list[dict[str, Any]],
) -> dict[str, str] | None:
    """Suggest git reset to last good commit — text only, never executed."""
    if not diagnostics or not diagnostics.get("cascade_root_event_id"):
        return None
    from cairn.outcomes.git import commit_before_timestamp

    root_id = diagnostics["cascade_root_event_id"]
    root_event = next(
        (e for e in events if e.get("event_id") == root_id or e.get("seq") == root_id),
        None,
    )
    before_ts = (root_event or {}).get("ts") or run.get("started_at")
    cwd = run.get("cwd") or run.get("project")
    sha = commit_before_timestamp(str(cwd) if cwd else None, str(before_ts) if before_ts else None)
    if not sha:
        return None
    return {
        "commit_sha": sha,
        "command": f"git reset --hard {sha}",
        "note": "Last commit before the detected cascade root — apply only with human approval",
    }


def _session_confidence(dq_row: sqlite3.Row | None, run: dict[str, Any]) -> dict[str, Any]:
    """Per-session provenance for confidence chips."""
    import json

    from cairn.ingest.tokenize import estimation_error_pct

    if dq_row is None:
        has_cost = bool(run.get("has_cost"))
        return {
            "pct_tokens_measured": None,
            "cost_source": "observed" if has_cost else "absent",
            "estimation_method": "exact" if has_cost else None,
            "estimation_error_pct": None,
        }
    notes: list[str] = []
    if dq_row["notes_json"]:
        try:
            notes = json.loads(str(dq_row["notes_json"]))
        except json.JSONDecodeError:
            notes = []
    method: str | None = "exact"
    err: float | None = None
    for note in notes:
        if "heuristic" in note:
            method = "heuristic"
            err = estimation_error_pct("heuristic", calibrated=True)
            break
        if "tiktoken" in note:
            method = "tiktoken"
            err = estimation_error_pct("tiktoken")
            break
    try:
        pct_est = dq_row["pct_tokens_estimated"]
    except IndexError:
        pct_est = None
    if pct_est is not None and float(pct_est) > 0 and method == "exact":
        method = "heuristic"
        err = estimation_error_pct("heuristic", calibrated=True)
    return {
        "pct_tokens_measured": dq_row["pct_tokens_measured"],
        "cost_source": dq_row["cost_source"],
        "estimation_method": method,
        "estimation_error_pct": err,
    }


def _fingerprint_section(
    conn: sqlite3.Connection, run_row: sqlite3.Row, events: list[dict[str, Any]]
) -> dict[str, Any]:
    """Per-session behavioral fingerprint vs project baseline (render-only)."""
    try:
        from cairn.metrics.fingerprint import (
            _baseline_vectors_for,
            detect_drift,
            fingerprint_session,
        )

        fp_row = conn.execute(
            "SELECT vector_json FROM fingerprints WHERE run_id = ?",
            (run_row["run_id"],),
        ).fetchone()
        if fp_row and fp_row["vector_json"]:
            import json

            vector = json.loads(fp_row["vector_json"])
        else:
            res = fingerprint_session(
                events,
                started_at=run_row["started_at"],
                ended_at=run_row["ended_at"],
                context_window=run_row["context_window"],
                reasoning_tokens=int(run_row["reasoning_tokens"] or 0),
                total_input_tokens=int(run_row["total_input_tokens"] or 0),
                total_output_tokens=int(run_row["total_output_tokens"] or 0),
            )
            vector = res.vector
        project = str(run_row["project"] or "")
        model = str(run_row["model"] or "")
        (run_row["started_at"] or "")[:10]
        baseline = _baseline_vectors_for(conn, project, model) if project else []
        drift = detect_drift(vector, baseline)
        labels = [
            "read",
            "edit",
            "bash",
            "search",
            "delete",
            "sub_agent",
            "read_write",
            "explore_exec",
            "retry",
            "error",
            "identical",
            "ctx_mean",
            "ctx_max",
            "ctx_slope",
            "ctx_final",
            "turns",
            "entropy",
            "reasoning",
            "avg_tokens",
            "out_in",
            "duration",
            "sub_count",
        ]
        baseline_mean = None
        if baseline:
            import numpy as np

            baseline_mean = [
                round(float(x), 4) for x in np.array(baseline).mean(axis=0).tolist()[: len(labels)]
            ]
        return {
            "vector": [round(float(x), 4) for x in vector[: len(labels)]],
            "labels": labels,
            "baseline_mean": baseline_mean,
            "distance": drift.distance,
            "d_squared": drift.d_squared,
            "threshold": drift.threshold,
            "drift": drift.drift,
            "kind": drift.kind,
            "baseline_n": len(baseline),
            "data_notes": drift.data_notes,
        }
    except Exception:  # noqa: BLE001
        return {
            "vector": None,
            "labels": [],
            "baseline_mean": None,
            "distance": None,
            "drift": False,
            "data_notes": ["fingerprint unavailable"],
        }


def _build_turns(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    user_text = ""
    turn_number = 0

    for event in events:
        if event.get("type") == "user_prompt" and current:
            turns.append(_turn_dict(turn_number, user_text, current))
            current = []
            turn_number += 1
        if event.get("type") == "user_prompt":
            user_text = str(event.get("text_inline") or "")
        current.append(event)

    if current:
        turns.append(_turn_dict(turn_number, user_text, current))
    return turns


def _turn_dict(turn_number: int, user_text: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    tool_count = sum(1 for e in events if e.get("type") == "tool_call")
    input_tokens = sum(int(e.get("input_tokens") or 0) for e in events)
    output_tokens = sum(int(e.get("output_tokens") or 0) for e in events)
    return {
        "turn_number": turn_number,
        "user_text": user_text,
        "preview": user_text[:80],
        "tool_count": tool_count,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "events": events,
    }


def _files_touched(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    files: dict[str, dict[str, int]] = {}
    for event in events:
        path = event.get("path_rel")
        if not path:
            continue
        entry = files.setdefault(str(path), {"reads": 0, "edits": 0})
        norm = event.get("tool_norm_name")
        if norm == "edit":
            entry["edits"] += 1
        elif norm in ("read", "search"):
            entry["reads"] += 1
    return [{"path": p, **counts} for p, counts in sorted(files.items())]


def build_session_graph(
    events: list[dict[str, Any]],
    turns: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    file_access: dict[str, dict[str, Any]] = {}

    for i, turn in enumerate(turns):
        nodes.append(
            {
                "id": f"turn-{i}",
                "type": "turn",
                "label": (turn.get("user_text") or "")[:40],
                "tool_count": turn.get("tool_count", 0),
                "tokens": turn.get("input_tokens", 0),
            }
        )
        if i > 0:
            edges.append({"source": f"turn-{i - 1}", "target": f"turn-{i}", "kind": "temporal"})

    for event in events:
        path = event.get("path_rel")
        if not path or event.get("type") not in ("tool_call", "file_snapshot"):
            continue
        turn_n = event.get("_turn_n", 0)
        access = file_access.setdefault(
            str(path),
            {"turns": set(), "reads": 0, "edits": 0},
        )
        access["turns"].add(turn_n)
        if event.get("tool_norm_name") == "edit":
            access["edits"] += 1
        else:
            access["reads"] += 1

    file_node_ids: set[str] = set()
    for path, access in file_access.items():
        if len(access["turns"]) >= 2 or access["edits"] > 0:
            fid = f"file:{path}"
            file_node_ids.add(fid)
            nodes.append(
                {
                    "id": fid,
                    "type": "file",
                    "label": path.split("/")[-1],
                    "path": path,
                    "edits": access["edits"],
                    "reads": access["reads"],
                }
            )

    seen_edges: set[str] = set()
    for event in events:
        path = event.get("path_rel")
        if not path:
            continue
        fid = f"file:{path}"
        if fid not in file_node_ids:
            continue
        turn_n = event.get("_turn_n", 0)
        kind = "edit" if event.get("tool_norm_name") == "edit" else "read"
        edge_id = f"turn-{turn_n}→{path}→{kind}"
        if edge_id in seen_edges:
            continue
        seen_edges.add(edge_id)
        edges.append(
            {
                "source": f"turn-{turn_n}",
                "target": fid,
                "kind": kind,
            }
        )

    return {"nodes": nodes, "edges": edges}
