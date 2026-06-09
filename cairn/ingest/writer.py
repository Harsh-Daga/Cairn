"""Sole SQLite mutator for capture ingest (R19.1, ADR 0008)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from cairn import __version__
from cairn.cache.cas import ContentAddressableStore
from cairn.ingest.normalizer import assign_seq
from cairn.ingest.parsers.claude_code import ParsedClaudeSession, ToolCallDraft
from cairn.ingest.parsers.codex import ParsedCodexSession
from cairn.ingest.parsers.cursor import ParsedCursorSession
from cairn.ingest.parsers.hermes import ParsedHermesSession
from cairn.ingest.project_paths import path_rel_to_repo, try_git_branch, try_git_commit
from cairn.ingest.types import ParsedAgentSession
from cairn.ingest.usage import ObservedUsage, extract_usage_dict
from cairn.ledger.ledger import new_run_id
from cairn.ledger.schema import migrate
from cairn.util.canonical import CAIRN_KEY_VERSION, canonical_json, hash_bytes, hash_obj


@dataclass(frozen=True)
class IngestResult:
    external_id: str
    run_id: str
    inserted: bool
    event_count: int


@dataclass(frozen=True)
class SessionSummary:
    run_id: str
    external_id: str
    source: str
    cwd: str | None
    git_branch: str | None
    git_commit: str | None
    started_at: str
    ended_at: str | None
    status: str
    model: str | None
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float | None
    trajectory_hash: str | None
    event_count: int


class CaptureWriter:
    """Append-only capture writes; never touches action_cache (invariant 20)."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        cairn_dir = self.project_root / ".cairn"
        cairn_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = cairn_dir / "ledger.db"
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        migrate(self._conn)
        self.cas = ContentAddressableStore(cairn_dir)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def session_exists(self, source: str, external_id: str) -> bool:
        row = self._conn.execute(
            """
            SELECT 1 FROM runs
            WHERE source = ? AND external_id = ?
            """,
            (source, external_id),
        ).fetchone()
        return row is not None

    def ingest_claude_session(self, parsed: ParsedClaudeSession) -> IngestResult:
        return self._ingest_session(
            source="claude-code",
            external_id=parsed.external_id,
            cwd=parsed.cwd,
            git_branch=parsed.git_branch,
            started_at=parsed.started_at,
            ended_at=parsed.ended_at,
            model=parsed.model,
            events=parsed.events,
            tool_calls=parsed.tool_calls,
            file_artifacts=parsed.file_artifacts,
            usage=parsed.usage.usage,
        )

    def ingest_codex_session(self, parsed: ParsedCodexSession) -> IngestResult:
        return self._ingest_session(
            source="codex",
            external_id=parsed.external_id,
            cwd=parsed.cwd,
            git_branch=None,
            started_at=parsed.started_at,
            ended_at=parsed.ended_at,
            model=parsed.model,
            events=parsed.events,
            tool_calls=parsed.tool_calls,
            file_artifacts=parsed.file_artifacts,
            usage=parsed.usage.usage,
        )

    def ingest_hermes_session(self, parsed: ParsedHermesSession) -> IngestResult:
        return self._ingest_session(
            source="hermes",
            external_id=parsed.external_id,
            cwd=parsed.cwd,
            git_branch=None,
            started_at=parsed.started_at,
            ended_at=parsed.ended_at,
            model=parsed.model,
            events=parsed.events,
            tool_calls=parsed.tool_calls,
            file_artifacts=parsed.file_artifacts,
            usage=parsed.usage.usage,
        )

    def ingest_agent_session(self, parsed: ParsedAgentSession) -> IngestResult:
        return self._ingest_session(
            source=parsed.source,
            external_id=parsed.external_id,
            cwd=parsed.cwd,
            git_branch=parsed.git_branch,
            started_at=parsed.started_at,
            ended_at=parsed.ended_at,
            model=parsed.model,
            events=parsed.events,
            tool_calls=parsed.tool_calls,
            file_artifacts=parsed.file_artifacts,
            usage=parsed.usage.usage,
        )

    def ingest_cursor_session(self, parsed: ParsedCursorSession) -> IngestResult:
        events = list(parsed.events)
        for link in parsed.sub_agent_links:
            events.append(
                {
                    "type": "sub_agent",
                    "parent_tool_use_id": link["parent_tool_use_id"],
                    "child_session_id": link["child_session_id"],
                    "child_source": link["child_source"],
                }
            )
        return self._ingest_session(
            source="cursor",
            external_id=parsed.external_id,
            cwd=parsed.cwd,
            git_branch=None,
            started_at=parsed.started_at,
            ended_at=parsed.ended_at,
            model=parsed.model,
            events=events,
            tool_calls=parsed.tool_calls,
            file_artifacts=parsed.file_artifacts,
            usage=parsed.usage.usage,
        )

    def load_file_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT path_rel, first_seq, last_seq, before_hash, after_hash
            FROM file_artifacts
            WHERE run_id = ?
            ORDER BY first_seq, path_rel
            """,
            (run_id,),
        ).fetchall()
        return [
            {
                "path_rel": str(row["path_rel"]),
                "first_seq": int(row["first_seq"]),
                "last_seq": int(row["last_seq"]),
                "before_hash": row["before_hash"],
                "after_hash": row["after_hash"],
                "event_seqs": _artifact_event_seqs(
                    int(row["first_seq"]),
                    int(row["last_seq"]),
                ),
            }
            for row in rows
        ]

    def begin_session(
        self,
        *,
        source: str,
        external_id: str,
        cwd: str | None,
    ) -> str:
        """Open or resume a live capture session (§11.2)."""
        existing = self._conn.execute(
            """
            SELECT run_id, status FROM runs
            WHERE source = ? AND external_id = ?
            """,
            (source, external_id),
        ).fetchone()
        if existing is not None:
            return str(existing["run_id"])

        run_id = new_run_id()
        now = datetime.now(UTC).isoformat()
        git_commit = try_git_commit(self.project_root)
        branch = try_git_branch(self.project_root)
        self._conn.execute(
            """
            INSERT INTO runs (
              run_id, kind, source, external_id, cwd, git_branch, git_commit,
              started_at, ended_at, status, trajectory_hash,
              total_cost, total_input_tokens, total_output_tokens,
              cairn_version, key_version
            )
            VALUES (?, 'capture', ?, ?, ?, ?, ?, ?, NULL, 'in_progress', NULL,
                    NULL, 0, 0, ?, ?)
            """,
            (
                run_id,
                source,
                external_id,
                cwd,
                branch,
                git_commit,
                now,
                __version__,
                CAIRN_KEY_VERSION,
            ),
        )
        self._conn.commit()
        return run_id

    def append_event(self, run_id: str, event: dict[str, Any]) -> int:
        """Append one event with the next monotonic ``seq``."""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM events WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        seq = int(row["n"]) if row else 1
        payload = dict(event)
        payload["seq"] = seq
        payload.pop("line_no", None)
        self._conn.execute(
            """
            INSERT INTO events (run_id, seq, event_type, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                run_id,
                seq,
                str(payload["type"]),
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ),
        )
        self._conn.commit()
        return seq

    def finish_session(self, run_id: str, *, status: str = "completed") -> None:
        """Finalize a live session and refresh trajectory mirror."""
        now = datetime.now(UTC).isoformat()
        events = self.load_events(run_id)
        row = self._conn.execute(
            "SELECT external_id, source, cwd, git_branch, git_commit FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return
        external_id = str(row["external_id"])
        source = str(row["source"])
        cwd = str(row["cwd"]) if row["cwd"] else str(self.project_root)
        usage = ObservedUsage()
        model = "unknown"
        for event in events:
            if event.get("type") == "assistant_message":
                model = str(event.get("model", model))
                raw_usage = event.get("usage")
                if isinstance(raw_usage, dict):
                    usage.add(extract_usage_dict(raw_usage))
        run_row = self._conn.execute(
            "SELECT started_at FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        started_at = str(run_row["started_at"]) if run_row else now
        trajectory = _build_trajectory(
            session_id=external_id,
            source=source,
            external_id=external_id,
            cwd=cwd,
            git_branch=str(row["git_branch"]) if row["git_branch"] else None,
            git_commit=str(row["git_commit"]) if row["git_commit"] else None,
            model=model,
            started_at=started_at,
            ended_at=now,
            status=status,
            usage=usage,
            events=events,
        )
        trajectory_hash = hash_obj(trajectory)
        self.cas.put(canonical_json(trajectory).encode("utf-8"))
        self._conn.execute(
            """
            UPDATE runs
            SET ended_at = ?, status = ?, trajectory_hash = ?,
                total_input_tokens = ?, total_output_tokens = ?, total_cost = ?
            WHERE run_id = ?
            """,
            (
                now,
                status,
                trajectory_hash,
                usage.input_tokens,
                usage.output_tokens,
                usage.cost,
                run_id,
            ),
        )
        self._conn.commit()
        self._write_session_mirror(external_id, trajectory)

    def record_file_before(
        self,
        run_id: str,
        path_rel: str,
        before_hash: str,
        seq: int,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO file_artifacts (
              run_id, path_rel, first_seq, last_seq, before_hash, after_hash
            )
            VALUES (?, ?, ?, ?, ?, NULL)
            ON CONFLICT(run_id, path_rel, last_seq) DO UPDATE SET
              before_hash = excluded.before_hash,
              first_seq = excluded.first_seq
            """,
            (run_id, path_rel, seq, seq, before_hash),
        )
        self._conn.commit()

    def record_file_after(
        self,
        run_id: str,
        path_rel: str,
        after_hash: str,
        seq: int,
    ) -> None:
        row = self._conn.execute(
            """
            SELECT rowid, first_seq, before_hash FROM file_artifacts
            WHERE run_id = ? AND path_rel = ?
            ORDER BY last_seq DESC LIMIT 1
            """,
            (run_id, path_rel),
        ).fetchone()
        if row is None:
            self._conn.execute(
                """
                INSERT INTO file_artifacts (
                  run_id, path_rel, first_seq, last_seq, before_hash, after_hash
                )
                VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (run_id, path_rel, seq, seq, after_hash),
            )
        else:
            self._conn.execute(
                """
                UPDATE file_artifacts
                SET after_hash = ?, last_seq = ?
                WHERE rowid = ?
                """,
                (after_hash, seq, int(row["rowid"])),
            )
        self._conn.commit()

    def has_tool_call(self, run_id: str, tool_use_id: str) -> bool:
        row = self._conn.execute(
            """
            SELECT 1 FROM events
            WHERE run_id = ? AND event_type = 'tool_call'
              AND json_extract(payload_json, '$.tool_use_id') = ?
            LIMIT 1
            """,
            (run_id, tool_use_id),
        ).fetchone()
        return row is not None

    def snapshot_file_hash(self, file_path: str, cwd: str | None) -> str | None:
        """Read file bytes and return CAS hash, or None if missing."""
        path = Path(file_path)
        if not path.is_absolute() and cwd:
            path = Path(cwd) / path
        if not path.is_file():
            return None
        return hash_bytes(path.read_bytes())

    def rel_path(self, file_path: str, cwd: str | None) -> str | None:
        path = Path(file_path)
        if not path.is_absolute():
            path = (Path(cwd) if cwd else self.project_root) / path
        return path_rel_to_repo(self.project_root, str(path.resolve()))

    def _ingest_session(
        self,
        *,
        source: str,
        external_id: str,
        cwd: str | None,
        git_branch: str | None,
        started_at: str | None,
        ended_at: str | None,
        model: str | None,
        events: list[dict[str, Any]],
        tool_calls: list[ToolCallDraft],
        file_artifacts: list[Any],
        usage: Any,
    ) -> IngestResult:
        existing = self._conn.execute(
            "SELECT run_id FROM runs WHERE source = ? AND external_id = ?",
            (source, external_id),
        ).fetchone()
        if existing is not None:
            run_id = str(existing["run_id"])
            count_row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            event_count = int(count_row["n"]) if count_row else 0
            return IngestResult(
                external_id=external_id,
                run_id=run_id,
                inserted=False,
                event_count=event_count,
            )

        run_id = new_run_id()
        seq_events = assign_seq(_strip_hints(events))
        git_commit = try_git_commit(self.project_root)
        branch = git_branch or try_git_branch(self.project_root)
        started = started_at or datetime.now(UTC).isoformat()
        status = "completed"
        trajectory = _build_trajectory(
            session_id=external_id,
            source=source,
            external_id=external_id,
            cwd=cwd or str(self.project_root),
            git_branch=branch,
            git_commit=git_commit,
            model=model,
            started_at=started,
            ended_at=ended_at,
            status=status,
            usage=usage,
            events=seq_events,
        )
        trajectory_hash = hash_obj(trajectory)
        self.cas.put(canonical_json(trajectory).encode("utf-8"))

        self._conn.execute(
            """
            INSERT INTO runs (
              run_id, kind, source, external_id, cwd, git_branch, git_commit,
              started_at, ended_at, status, trajectory_hash,
              total_cost, total_input_tokens, total_output_tokens,
              cairn_version, key_version
            )
            VALUES (?, 'capture', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                source,
                external_id,
                cwd,
                branch,
                git_commit,
                started,
                ended_at,
                status,
                trajectory_hash,
                usage.cost,
                usage.input_tokens,
                usage.output_tokens,
                __version__,
                CAIRN_KEY_VERSION,
            ),
        )

        for event in seq_events:
            self._conn.execute(
                """
                INSERT INTO events (run_id, seq, event_type, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    run_id,
                    int(event["seq"]),
                    str(event["type"]),
                    json.dumps(event, sort_keys=True, separators=(",", ":")),
                ),
            )

        tool_seq = 0
        tool_by_id = {tc.tool_use_id: tc for tc in tool_calls}
        for event in seq_events:
            if event["type"] == "tool_result":
                tool_use_id = str(event["tool_use_id"])
                draft = tool_by_id.get(tool_use_id)
                tool_seq += 1
                self._conn.execute(
                    """
                    INSERT INTO tool_calls (
                      run_id, node_id, seq, tool_id, name, args_hash,
                      result_hash, is_error, duration_ms
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        run_id,
                        run_id,
                        tool_seq,
                        tool_use_id,
                        draft.name if draft else None,
                        draft.args_hash if draft else None,
                        event.get("result_hash"),
                        1 if event.get("is_error") else 0,
                    ),
                )

        for artifact in file_artifacts:
            self._conn.execute(
                """
                INSERT INTO file_artifacts (
                  run_id, path_rel, first_seq, last_seq, before_hash, after_hash
                )
                VALUES (?, ?, ?, ?, NULL, NULL)
                """,
                (
                    run_id,
                    artifact.path_rel,
                    artifact.first_seq_hint,
                    artifact.last_seq_hint,
                ),
            )

        self._conn.commit()
        self._write_session_mirror(external_id, trajectory)
        return IngestResult(
            external_id=external_id,
            run_id=run_id,
            inserted=True,
            event_count=len(seq_events),
        )

    def _write_session_mirror(self, external_id: str, trajectory: dict[str, Any]) -> None:
        sessions_dir = self.project_root / ".cairn" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        out = sessions_dir / f"{external_id}.json"
        out.write_text(canonical_json(trajectory) + "\n", encoding="utf-8")

    def list_sessions(
        self,
        *,
        limit: int = 20,
        source: str | None = None,
    ) -> list[SessionSummary]:
        if source:
            rows = self._conn.execute(
                """
                SELECT r.*, (
                  SELECT COUNT(*) FROM events e WHERE e.run_id = r.run_id
                ) AS event_count
                FROM runs r
                WHERE r.kind = 'capture' AND r.source = ?
                ORDER BY r.started_at DESC
                LIMIT ?
                """,
                (source, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT r.*, (
                  SELECT COUNT(*) FROM events e WHERE e.run_id = r.run_id
                ) AS event_count
                FROM runs r
                WHERE r.kind = 'capture'
                ORDER BY r.started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_summary(r) for r in rows]

    def load_session_by_external_id(self, session_id: str) -> SessionSummary | None:
        row = self._conn.execute(
            """
            SELECT r.*, (
              SELECT COUNT(*) FROM events e WHERE e.run_id = r.run_id
            ) AS event_count
            FROM runs r
            WHERE r.kind = 'capture' AND r.external_id = ?
            """,
            (session_id,),
        ).fetchone()
        return _row_to_summary(row) if row else None

    def load_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT payload_json FROM events
            WHERE run_id = ?
            ORDER BY seq
            """,
            (run_id,),
        ).fetchall()
        return [
            cast(dict[str, Any], json.loads(str(r["payload_json"])))
            for r in rows
        ]

    def load_trajectory(self, session_id: str) -> dict[str, Any] | None:
        mirror = self.project_root / ".cairn" / "sessions" / f"{session_id}.json"
        if mirror.is_file():
            return cast(
                dict[str, Any],
                json.loads(mirror.read_text(encoding="utf-8")),
            )
        summary = self.load_session_by_external_id(session_id)
        if summary is None or summary.trajectory_hash is None:
            return None
        raw = self.cas.read(summary.trajectory_hash)
        if raw is None:
            return None
        return cast(dict[str, Any], json.loads(raw.decode("utf-8")))


def _artifact_event_seqs(first_seq: int, last_seq: int) -> list[int]:
    if first_seq == last_seq:
        return [first_seq]
    return [first_seq, last_seq]


def _strip_hints(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in event.items() if k != "line_no"} for event in events]


def _build_trajectory(
    *,
    session_id: str,
    source: str,
    external_id: str,
    cwd: str,
    git_branch: str | None,
    git_commit: str | None,
    model: str | None,
    started_at: str,
    ended_at: str | None,
    status: str,
    usage: Any,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": 2,
        "schema": "cairn-trajectory",
        "session_id": session_id,
        "source": source,
        "external_id": external_id,
        "cwd": cwd,
        "git": {
            "branch": git_branch,
            "commit": git_commit,
            "dirty": False,
        },
        "model": model or "unknown",
        "params": None,
        "started_at": started_at,
        "ended_at": ended_at,
        "status": status,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost": usage.cost,
        },
        "events": events,
    }


def _row_to_summary(row: sqlite3.Row) -> SessionSummary:
    model: str | None = None
    traj_hash = row["trajectory_hash"]
    if traj_hash:
        # model stored in trajectory mirror; fallback unknown in list view
        model = None
    return SessionSummary(
        run_id=str(row["run_id"]),
        external_id=str(row["external_id"]) if row["external_id"] else "",
        source=str(row["source"]) if row["source"] else "",
        cwd=str(row["cwd"]) if row["cwd"] else None,
        git_branch=str(row["git_branch"]) if row["git_branch"] else None,
        git_commit=str(row["git_commit"]) if row["git_commit"] else None,
        started_at=str(row["started_at"]),
        ended_at=str(row["ended_at"]) if row["ended_at"] else None,
        status=str(row["status"]),
        model=model,
        total_input_tokens=int(row["total_input_tokens"] or 0),
        total_output_tokens=int(row["total_output_tokens"] or 0),
        total_cost=row["total_cost"],
        trajectory_hash=str(traj_hash) if traj_hash else None,
        event_count=int(row["event_count"]),
    )
