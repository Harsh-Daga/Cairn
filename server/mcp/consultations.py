"""Privacy-minimal MCP consultation events and writable ingest bridge."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from server.util.ids import new_ulid

if TYPE_CHECKING:
    from server.mcp.tools import ToolsContext

_SIDECAR = Path(".cairn/mcp-events.jsonl")


def record_consultation(ctx: ToolsContext, tool_name: str) -> None:
    """Append a marker without mutating the read-only MCP ledger connection."""
    if ctx.workspace_id is None:
        return
    row = ctx.conn.execute(
        """SELECT t.trace_id, COALESCE(MAX(s.seq), 0) AS after_seq
           FROM traces t LEFT JOIN spans s ON s.trace_id = t.trace_id
           WHERE t.workspace_id = ?
           GROUP BY t.trace_id, t.started_at
           ORDER BY t.started_at DESC LIMIT 1""",
        (ctx.workspace_id,),
    ).fetchone()
    if row is None:
        return
    event = {
        "event_id": new_ulid(),
        "trace_id": str(row["trace_id"]),
        "after_seq": int(row["after_seq"]),
        "tool_name": tool_name,
        "called_at": datetime.now(UTC).isoformat(),
    }
    path = ctx.workspace_root / _SIDECAR
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, separators=(",", ":")) + "\n")
    except OSError:
        # Observability must never make an MCP tool unavailable.
        return


def import_consultations(
    conn: sqlite3.Connection, workspace_root: Path, workspace_id: str
) -> int:
    """Idempotently import sidecar events through Cairn's normal writer path."""
    path = workspace_root / _SIDECAR
    if not path.is_file():
        return 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0

    imported = 0
    imported_at = datetime.now(UTC).isoformat()
    for line in lines:
        event = _valid_event(line)
        if event is None:
            continue
        trace = conn.execute(
            "SELECT 1 FROM traces WHERE trace_id = ? AND workspace_id = ?",
            (event["trace_id"], workspace_id),
        ).fetchone()
        if trace is None:
            continue
        cursor = conn.execute(
            """INSERT OR IGNORE INTO mcp_consultations (
                 event_id, workspace_id, trace_id, after_seq, tool_name, called_at, imported_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                event["event_id"],
                workspace_id,
                event["trace_id"],
                event["after_seq"],
                event["tool_name"],
                event["called_at"],
                imported_at,
            ),
        )
        imported += cursor.rowcount
    return imported


def _valid_event(line: str) -> dict[str, Any] | None:
    try:
        value = json.loads(line)
        event_id = str(value["event_id"])
        trace_id = str(value["trace_id"])
        tool_name = str(value["tool_name"])
        called_at = str(value["called_at"])
        after_seq = int(value["after_seq"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if not event_id or not trace_id or not tool_name.startswith("cairn_") or after_seq < 0:
        return None
    return {
        "event_id": event_id,
        "trace_id": trace_id,
        "tool_name": tool_name,
        "called_at": called_at,
        "after_seq": after_seq,
    }
