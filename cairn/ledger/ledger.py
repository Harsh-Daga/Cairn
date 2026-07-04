"""Cairn v3 ledger — SQLite wrapper with auto-migration."""

from __future__ import annotations

import secrets
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cairn.ledger.schema import FTS_AVAILABLE, migrate


def new_run_id() -> str:
    ts = int(time.time() * 1000)
    return f"{ts:013d}-{secrets.token_hex(8)}"


def try_git_commit(project_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


@dataclass(frozen=True)
class RunRow:
    run_id: str
    source: str
    external_id: str | None
    project: str | None
    model: str | None
    started_at: str | None
    ended_at: str | None
    status: str
    total_input_tokens: int
    total_output_tokens: int
    output_estimated: bool
    cache_read_tokens: int
    cache_creation_tokens: int
    reasoning_tokens: int
    total_cost: float
    has_cost: bool
    has_timestamps: bool
    context_window: int | None
    peak_context_pct: float | None
    rate_limit_used_pct: float | None
    rate_limit_window_min: int | None
    rate_limit_resets_at: str | None
    plan_type: str | None
    waste_tokens: int
    event_count: int
    tool_call_count: int
    tool_error_count: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> RunRow:
        return cls(
            run_id=str(row["run_id"]),
            source=str(row["source"]),
            external_id=row["external_id"],
            project=row["project"],
            model=row["model"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            status=str(row["status"]),
            total_input_tokens=int(row["total_input_tokens"] or 0),
            total_output_tokens=int(row["total_output_tokens"] or 0),
            output_estimated=bool(row["output_estimated"]),
            cache_read_tokens=int(row["cache_read_tokens"] or 0),
            cache_creation_tokens=int(row["cache_creation_tokens"] or 0),
            reasoning_tokens=int(row["reasoning_tokens"] or 0),
            total_cost=float(row["total_cost"] or 0),
            has_cost=bool(row["has_cost"]),
            has_timestamps=bool(row["has_timestamps"]),
            context_window=row["context_window"],
            peak_context_pct=row["peak_context_pct"],
            rate_limit_used_pct=row["rate_limit_used_pct"],
            rate_limit_window_min=row["rate_limit_window_min"],
            rate_limit_resets_at=row["rate_limit_resets_at"],
            plan_type=row["plan_type"],
            waste_tokens=int(row["waste_tokens"] or 0),
            event_count=int(row["event_count"] or 0),
            tool_call_count=int(row["tool_call_count"] or 0),
            tool_error_count=int(row["tool_error_count"] or 0),
        )


class Ledger:
    """Thin SQLite ledger for capture runs, events, rollups, and optimizations."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        migrate(self._conn)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    @property
    def fts_available(self) -> bool:
        return FTS_AVAILABLE

    def close(self) -> None:
        self._conn.close()

    def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        source: str | None = None,
        project: str | None = None,
        since: str | None = None,
    ) -> list[RunRow]:
        clauses = ["1=1"]
        params: list[Any] = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if project:
            clauses.append("project = ?")
            params.append(project)
        if since:
            clauses.append("started_at >= ?")
            params.append(since)
        where = " AND ".join(clauses)
        params.extend([limit, offset])
        rows = self._conn.execute(
            f"""
            SELECT * FROM runs
            WHERE {where}
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return [RunRow.from_row(r) for r in rows]

    def get_run(self, run_id: str) -> RunRow | None:
        row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return RunRow.from_row(row) if row else None

    def load_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM events WHERE run_id = ? ORDER BY seq
            """,
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_runs(self, *, since: str | None = None) -> int:
        if since:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM runs WHERE started_at >= ?", (since,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()
        return int(row[0]) if row else 0
