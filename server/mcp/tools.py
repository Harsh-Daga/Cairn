"""MCP tool implementations for the trace and span schema."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass
class ToolsContext:
    conn: sqlite3.Connection
    workspace_root: Path
    workspace_id: str | None

    def close(self) -> None:
        self.conn.close()


def open_context(start_cwd: Path) -> ToolsContext:
    """Open a read-only ledger for the workspace containing *start_cwd*."""
    root = start_cwd.resolve()
    db_path = root / ".cairn" / "cairn.db"
    if db_path.is_file():
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    workspace_id = _resolve_workspace_id(conn)
    return ToolsContext(conn=conn, workspace_root=root, workspace_id=workspace_id)


def _resolve_workspace_id(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT workspace_id FROM workspaces ORDER BY created_at LIMIT 1").fetchone()
    return str(row["workspace_id"]) if row else None


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "cairn_have_i_read",
        "description": "Have I already read this file in recent sessions?",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "within_session": {"type": "boolean"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "cairn_my_recurring_waste",
        "description": "Top recurring waste patterns for this workspace.",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    },
    {
        "name": "cairn_project_primer",
        "description": "Compressed project primer: waste, hotspots, fingerprint, rules.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
        },
    },
    {
        "name": "cairn_session_so_far",
        "description": "Summary of the latest session so far (cost, context, recent spans).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cairn_should_i_stop",
        "description": "Mid-session loop guard based on the latest trace tail.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cairn_project_conventions",
        "description": "Applied managed-block rules and experiment conventions.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def list_tools() -> list[dict[str, Any]]:
    return [
        {"name": t["name"], "description": t["description"], "schema": t["inputSchema"]}
        for t in TOOL_SCHEMAS
    ]


def call_tool(ctx: ToolsContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
    dispatch = {
        "cairn_have_i_read": _have_i_read,
        "cairn_my_recurring_waste": _my_recurring_waste,
        "cairn_project_primer": _project_primer,
        "cairn_session_so_far": _session_so_far,
        "cairn_should_i_stop": _should_i_stop,
        "cairn_project_conventions": _project_conventions,
    }
    fn = dispatch.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(ctx, args)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _have_i_read(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    path = str(args.get("path") or "")
    within_session = bool(args.get("within_session"))
    if not path:
        return {"read": False, "reason": "no path provided"}
    rel = _rel_path(ctx.workspace_root, path)
    ws_clause = ""
    params: list[Any] = [rel]
    if ctx.workspace_id:
        ws_clause = "AND t.workspace_id = ?"
        params.append(ctx.workspace_id)
    sql = f"""
        SELECT s.seq, s.started_at, s.text_inline, t.trace_id, t.started_at AS trace_started
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE s.kind = 'tool_call'
          AND s.path_rel = ?
          AND (s.name IN ('read','search','grep','glob') OR s.name LIKE '%read%')
          {ws_clause}
        ORDER BY s.seq
    """
    if within_session:
        last = ctx.conn.execute(
            f"SELECT trace_id FROM traces {'WHERE workspace_id = ?' if ctx.workspace_id else ''} "
            "ORDER BY started_at DESC LIMIT 1",
            [ctx.workspace_id] if ctx.workspace_id else [],
        ).fetchone()
        if last is None:
            return {"read": False, "reason": "no sessions", "path": rel}
        sql += " AND t.trace_id = ?"
        params.append(str(last["trace_id"]))
    rows = ctx.conn.execute(sql, params).fetchall()
    if not rows:
        return {"read": False, "path": rel, "times": 0}
    return {
        "read": True,
        "path": rel,
        "times": len(rows),
        "last": {"turn": int(rows[-1]["seq"]), "ts": rows[-1]["started_at"]},
    }


def _my_recurring_waste(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit") or 3)
    ws_clause = "WHERE t.workspace_id = ?" if ctx.workspace_id else ""
    params: list[Any] = [ctx.workspace_id] if ctx.workspace_id else []
    rows = ctx.conn.execute(
        f"""
        SELECT s.waste_category AS cat, COUNT(*) AS n, SUM(s.waste_tokens) AS tokens
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        {ws_clause}
        {"AND" if ws_clause else "WHERE"} s.waste_category IS NOT NULL
        GROUP BY s.waste_category
        ORDER BY tokens DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    patterns = [
        {"pattern": r["cat"], "count": int(r["n"]), "tokens": int(r["tokens"] or 0)} for r in rows
    ]
    if not patterns:
        return {"patterns": [], "note": "no waste patterns recorded yet"}
    return {"patterns": patterns}


def _project_primer(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    project = str(args.get("project") or ctx.workspace_root.name)
    waste = _my_recurring_waste(ctx, {"limit": 3}).get("patterns", [])
    hotspots = _hotspot_paths(ctx, project, limit=5)
    baseline = _fingerprint_summary(ctx, project)
    rules = _project_conventions(ctx, {}).get("rules", [])
    primer = (
        f"# {project} — Cairn primer\n\n"
        f"Recurring waste: {', '.join(w['pattern'] for w in waste) or 'none yet'}.\n"
        f"Hotspot files: {', '.join(h['path'] for h in hotspots) or 'none yet'}.\n"
        f"Active managed rules: {len(rules)}.\n"
    )
    return {
        "project": project,
        "primer": primer,
        "waste_patterns": waste,
        "hotspot_files": hotspots,
        "fingerprint_baseline": baseline,
        "active_rules": rules,
    }


def _session_so_far(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    del args
    ws = "WHERE workspace_id = ?" if ctx.workspace_id else ""
    params: list[Any] = [ctx.workspace_id] if ctx.workspace_id else []
    trace = ctx.conn.execute(
        f"SELECT * FROM traces {ws} ORDER BY started_at DESC LIMIT 1",
        params,
    ).fetchone()
    if trace is None:
        return {"trace_id": None, "note": "no sessions in ledger"}
    trace_id = str(trace["trace_id"])
    tail = ctx.conn.execute(
        "SELECT seq, kind, name, status, input_tokens, output_tokens, waste_tokens "
        "FROM spans WHERE trace_id = ? ORDER BY seq DESC LIMIT 8",
        (trace_id,),
    ).fetchall()
    return {
        "trace_id": trace_id,
        "title": trace["title"],
        "cost": float(trace["cost"] or 0),
        "input_tokens": int(trace["input_tokens"] or 0),
        "output_tokens": int(trace["output_tokens"] or 0),
        "span_count": int(trace["span_count"] or 0),
        "recent_spans": [dict(r) for r in reversed(tail)],
    }


def _should_i_stop(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    from server.improve.detectors.registry import detect_live_stop_pattern

    del args
    ws = "WHERE workspace_id = ?" if ctx.workspace_id else ""
    params: list[Any] = [ctx.workspace_id] if ctx.workspace_id else []
    trace = ctx.conn.execute(
        f"SELECT trace_id FROM traces {ws} ORDER BY started_at DESC LIMIT 1",
        params,
    ).fetchone()
    if trace is None:
        return {"should_stop": False, "reason": "insufficient signal"}
    trace_id = str(trace["trace_id"])
    rows = ctx.conn.execute(
        """SELECT seq, kind, name, status, args_hash, text_hash
           FROM spans WHERE trace_id = ? ORDER BY seq DESC LIMIT 50""",
        (trace_id,),
    ).fetchall()
    ordered = [dict(row) for row in reversed(rows)]
    detection = detect_live_stop_pattern(ordered)
    if detection is None:
        return {
            "should_stop": False,
            "trace_id": trace_id,
            "pattern": None,
            "count": 0,
            "first_seen_seq": None,
            "advice": (
                "No retry loop, identical-call pattern, error streak, or failing command detected."
            ),
        }
    return {
        "should_stop": True,
        "trace_id": trace_id,
        "pattern": detection.pattern,
        "count": detection.count,
        "first_seen_seq": detection.first_seen_seq,
        "advice": detection.advice,
    }


def _project_conventions(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    del args
    rows = ctx.conn.execute(
        "SELECT experiment_id, target_file, block_key, kind, status, applied_at "
        "FROM experiments WHERE status IN ('applied','measuring','verdict') "
        "ORDER BY applied_at DESC"
    ).fetchall()
    rules = [
        {
            "experiment_id": r["experiment_id"],
            "target_file": r["target_file"],
            "block_key": r["block_key"],
            "kind": r["kind"],
            "status": r["status"],
            "applied_at": r["applied_at"],
            "age_days": _age_days(r["applied_at"]),
        }
        for r in rows
    ]
    if not rules:
        return {"rules": [], "note": "no applied managed rules"}
    return {"rules": rules}


def _rel_path(root: Path, path: str) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(root).as_posix()
        except ValueError:
            return path
    return path


def _hotspot_paths(ctx: ToolsContext, project: str, *, limit: int) -> list[dict[str, Any]]:
    ws = "AND t.workspace_id = ?" if ctx.workspace_id else ""
    params: list[Any] = [project]
    if ctx.workspace_id:
        params.append(ctx.workspace_id)
    rows = ctx.conn.execute(
        f"""
        SELECT s.path_rel AS path, COUNT(*) AS n, SUM(s.waste_tokens) AS waste
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE s.path_rel IS NOT NULL AND t.project = ? {ws}
        GROUP BY s.path_rel
        ORDER BY waste DESC, n DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [
        {"path": r["path"], "reads": int(r["n"]), "waste_tokens": int(r["waste"] or 0)}
        for r in rows
    ]


def _fingerprint_summary(ctx: ToolsContext, project: str) -> dict[str, Any] | None:
    row = ctx.conn.execute(
        """
        SELECT read_write_ratio, exploration_ratio, retry_rate, tool_entropy, turn_count
        FROM fingerprints WHERE project = ? ORDER BY ts DESC LIMIT 1
        """,
        (project,),
    ).fetchone()
    if row is None:
        return None
    return {
        "read_write_ratio": row["read_write_ratio"],
        "exploration_ratio": row["exploration_ratio"],
        "retry_rate": row["retry_rate"],
        "tool_entropy": row["tool_entropy"],
        "turn_count": row["turn_count"],
    }


def _age_days(ts: str | None) -> int | None:
    if not ts:
        return None
    try:
        d = date.fromisoformat(str(ts)[:10])
    except (ValueError, TypeError):
        return None
    return (date.today() - d).days
