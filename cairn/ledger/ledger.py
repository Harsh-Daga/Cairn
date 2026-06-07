"""Ledger: open/migrate; begin_run/finish_run; record_node; cas_ref (R14)."""

from __future__ import annotations

import json
import secrets
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from cairn import __version__
from cairn.cache.action_cache import ActionCache
from cairn.ledger.schema import migrate
from cairn.util.canonical import CAIRN_KEY_VERSION

RunStatus = Literal["running", "success", "partial", "failed"]
NodeStatus = Literal["ran", "cached", "skipped", "error"]


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
class RunSummary:
    run_id: str
    started_at: str
    ended_at: str | None
    status: RunStatus
    total_cost: float | None
    total_input_tokens: int
    total_output_tokens: int
    cairn_version: str
    key_version: int
    git_commit: str | None


@dataclass(frozen=True)
class NodeRecord:
    run_id: str
    node_id: str
    step: str
    item_id: str | None
    kind: str
    action_key: str
    output_hash: str | None
    status: NodeStatus
    model: str
    params_json: str
    input_tokens: int
    output_tokens: int
    cost: float | None
    duration_ms: int | None
    started_at: str
    ended_at: str
    rendered_prompt: str
    system_prompt: str


class Ledger:
    """SQLite ledger shared with the Action Cache (one file, one connection)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        migrate(self._conn)
        self.ac = ActionCache(self._conn)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def begin_run(self, project_root: Path) -> str:
        run_id = new_run_id()
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO runs (
              run_id, kind, started_at, ended_at, status,
              total_cost, total_input_tokens, total_output_tokens,
              cairn_version, key_version, git_commit
            )
            VALUES (?, 'build', ?, NULL, 'running', NULL, 0, 0, ?, ?, ?)
            """,
            (
                run_id,
                now,
                __version__,
                CAIRN_KEY_VERSION,
                try_git_commit(project_root),
            ),
        )
        self._conn.commit()
        return run_id

    def record_node(
        self,
        run_id: str,
        *,
        node_id: str,
        step: str,
        item_id: str | None,
        kind: str,
        action_key: str,
        output_hash: str | None,
        status: NodeStatus,
        model: str,
        params: dict[str, Any],
        input_tokens: int,
        output_tokens: int,
        cost: float | None,
        duration_ms: int | None,
        started_at: str,
        ended_at: str,
        rendered_prompt: str,
        system_prompt: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO nodes (
              run_id, node_id, step, item_id, kind, action_key, output_hash,
              status, model, params_json, input_tokens, output_tokens,
              cost, duration_ms, started_at, ended_at, rendered_prompt, system_prompt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                node_id,
                step,
                item_id,
                kind,
                action_key,
                output_hash,
                status,
                model,
                json.dumps(params, sort_keys=True, separators=(",", ":")),
                input_tokens,
                output_tokens,
                cost,
                duration_ms,
                started_at,
                ended_at,
                rendered_prompt,
                system_prompt,
            ),
        )
        self._conn.commit()

    def record_cas_ref(self, output_hash: str, run_id: str, node_id: str) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO cas_refs (output_hash, run_id, node_id)
            VALUES (?, ?, ?)
            """,
            (output_hash, run_id, node_id),
        )
        self._conn.commit()

    def finish_run(
        self,
        run_id: str,
        status: RunStatus,
        *,
        total_cost: float | None,
        total_input_tokens: int,
        total_output_tokens: int,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            UPDATE runs
            SET ended_at = ?, status = ?,
                total_cost = ?, total_input_tokens = ?, total_output_tokens = ?
            WHERE run_id = ?
            """,
            (
                now,
                status,
                total_cost,
                total_input_tokens,
                total_output_tokens,
                run_id,
            ),
        )
        self._conn.commit()

    def list_runs(self, limit: int = 20) -> list[RunSummary]:
        rows = self._conn.execute(
            """
            SELECT run_id, started_at, ended_at, status,
                   total_cost, total_input_tokens, total_output_tokens,
                   cairn_version, key_version, git_commit
            FROM runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            RunSummary(
                run_id=str(r["run_id"]),
                started_at=str(r["started_at"]),
                ended_at=str(r["ended_at"]) if r["ended_at"] else None,
                status=str(r["status"]),  # type: ignore[arg-type]
                total_cost=r["total_cost"],
                total_input_tokens=int(r["total_input_tokens"]),
                total_output_tokens=int(r["total_output_tokens"]),
                cairn_version=str(r["cairn_version"]),
                key_version=int(r["key_version"]),
                git_commit=str(r["git_commit"]) if r["git_commit"] else None,
            )
            for r in rows
        ]

    def latest_run_id(self) -> str | None:
        row = self._conn.execute(
            "SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return str(row["run_id"]) if row else None

    def load_run(self, run_id: str) -> tuple[RunSummary, list[NodeRecord]]:
        run_row = self._conn.execute(
            """
            SELECT run_id, started_at, ended_at, status,
                   total_cost, total_input_tokens, total_output_tokens,
                   cairn_version, key_version, git_commit
            FROM runs WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if run_row is None:
            msg = f"run not found: {run_id}"
            raise KeyError(msg)
        summary = RunSummary(
            run_id=str(run_row["run_id"]),
            started_at=str(run_row["started_at"]),
            ended_at=str(run_row["ended_at"]) if run_row["ended_at"] else None,
            status=str(run_row["status"]),  # type: ignore[arg-type]
            total_cost=run_row["total_cost"],
            total_input_tokens=int(run_row["total_input_tokens"]),
            total_output_tokens=int(run_row["total_output_tokens"]),
            cairn_version=str(run_row["cairn_version"]),
            key_version=int(run_row["key_version"]),
            git_commit=str(run_row["git_commit"]) if run_row["git_commit"] else None,
        )
        node_rows = self._conn.execute(
            """
            SELECT run_id, node_id, step, item_id, kind, action_key, output_hash,
                   status, model, params_json, input_tokens, output_tokens,
                   cost, duration_ms, started_at, ended_at, rendered_prompt, system_prompt
            FROM nodes WHERE run_id = ?
            ORDER BY node_id
            """,
            (run_id,),
        ).fetchall()
        nodes = [
            NodeRecord(
                run_id=str(r["run_id"]),
                node_id=str(r["node_id"]),
                step=str(r["step"]),
                item_id=str(r["item_id"]) if r["item_id"] else None,
                kind=str(r["kind"]),
                action_key=str(r["action_key"]),
                output_hash=str(r["output_hash"]) if r["output_hash"] else None,
                status=str(r["status"]),  # type: ignore[arg-type]
                model=str(r["model"]),
                params_json=str(r["params_json"]),
                input_tokens=int(r["input_tokens"]),
                output_tokens=int(r["output_tokens"]),
                cost=r["cost"],
                duration_ms=int(r["duration_ms"]) if r["duration_ms"] is not None else None,
                started_at=str(r["started_at"]),
                ended_at=str(r["ended_at"]),
                rendered_prompt=str(r["rendered_prompt"]),
                system_prompt=str(r["system_prompt"]),
            )
            for r in node_rows
        ]
        return summary, nodes

    def node_count(self, run_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM nodes WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return int(row["n"]) if row else 0
