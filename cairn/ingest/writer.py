"""Sole SQLite mutator for capture ingest — v3 flat events schema."""

from __future__ import annotations

import contextlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cairn.ingest.data_quality import PARSER_VERSION, compute_data_quality
from cairn.ingest.normalizer import assign_seq
from cairn.ingest.parsers.claude_code import ParsedClaudeSession, ToolCallDraft
from cairn.ingest.parsers.cline_family import ParsedClineSession
from cairn.ingest.parsers.codex import ParsedCodexSession
from cairn.ingest.parsers.cursor import ParsedCursorSession
from cairn.ingest.parsers.gemini_cli import ParsedGeminiSession
from cairn.ingest.parsers.hermes import ParsedHermesSession
from cairn.ingest.parsers.openclaw import ParsedOpenClawSession
from cairn.ingest.project_paths import path_rel_to_repo, try_git_branch, try_git_commit
from cairn.ingest.types import ParsedAgentSession
from cairn.ingest.usage import ObservedUsage, extract_usage_dict
from cairn.ledger.ledger import new_run_id
from cairn.ledger.schema import FTS_AVAILABLE, migrate
from cairn.metrics.constants import normalize_tool_name
from cairn.pricing.engine import estimate_cost, load_overrides

_HAS_COST_SOURCES = frozenset({"claude-code", "codex"})
_TEXT_INLINE_MAX = 500
_READ_NORM = frozenset({"read", "search"})
_WRITE_NORM = frozenset({"edit", "delete"})


@dataclass(frozen=True)
class IngestResult:
    external_id: str
    run_id: str
    inserted: bool
    event_count: int
    refreshed: bool = False


@dataclass(frozen=True)
class SessionSummary:
    run_id: str
    external_id: str
    source: str
    project: str | None
    cwd: str | None
    git_branch: str | None
    git_commit: str | None
    started_at: str
    ended_at: str | None
    status: str
    model: str | None
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    has_cost: bool
    waste_tokens: int
    event_count: int
    tool_call_count: int
    tool_error_count: int


class CaptureWriter:
    """Write capture sessions to the v3 ledger."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        cairn_dir = self.project_root / ".cairn"
        cairn_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = cairn_dir / "ledger.db"
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        migrate(self._conn)
        self._pricing_overrides = load_overrides(self.project_root)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def session_exists(self, source: str, external_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM runs WHERE source = ? AND external_id = ?",
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
            usage=parsed.usage.usage,
            context_window=parsed.context_window,
            rate_limit_used_pct=parsed.rate_limit_used_pct,
            rate_limit_window_min=parsed.rate_limit_window_min,
            rate_limit_resets_at=parsed.rate_limit_resets_at,
            plan_type=parsed.plan_type,
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
            usage=parsed.usage.usage,
        )

    def ingest_gemini_session(self, parsed: ParsedGeminiSession) -> IngestResult:
        return self._ingest_session(
            source="gemini",
            external_id=parsed.external_id,
            cwd=parsed.cwd,
            git_branch=parsed.git_branch,
            started_at=parsed.started_at,
            ended_at=parsed.ended_at,
            model=parsed.model,
            events=parsed.events,
            tool_calls=parsed.tool_calls,
            usage=parsed.usage.usage,
        )

    def ingest_cline_session(self, parsed: ParsedClineSession) -> IngestResult:
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
            usage=parsed.usage.usage,
        )

    def ingest_openclaw_session(self, parsed: ParsedOpenClawSession) -> IngestResult:
        return self._ingest_session(
            source="openclaw",
            external_id=parsed.external_id,
            cwd=parsed.cwd,
            git_branch=parsed.git_branch,
            started_at=parsed.started_at,
            ended_at=parsed.ended_at,
            model=parsed.model,
            events=parsed.events,
            tool_calls=parsed.tool_calls,
            usage=parsed.usage.usage,
        )

    def ingest_cursor_session(
        self, parsed: ParsedCursorSession, *, force_refresh: bool = False
    ) -> IngestResult:
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
        status = "best-of-n-subagent" if parsed.is_best_of_n_subcomposer else "completed"
        existing = self._conn.execute(
            "SELECT run_id FROM runs WHERE source = ? AND external_id = ?",
            ("cursor", parsed.external_id),
        ).fetchone()
        if existing is not None:
            run_id = str(existing["run_id"])
            if not force_refresh:
                count_row = self._conn.execute(
                    "SELECT COUNT(*) AS n FROM events WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                event_count = int(count_row["n"]) if count_row else 0
                return IngestResult(
                    external_id=parsed.external_id,
                    run_id=run_id,
                    inserted=False,
                    event_count=event_count,
                )
            return self._replace_session(
                run_id=run_id,
                source="cursor",
                external_id=parsed.external_id,
                cwd=parsed.cwd,
                git_branch=None,
                started_at=parsed.started_at,
                ended_at=parsed.ended_at,
                model=parsed.model or "cursor",
                events=events,
                tool_calls=parsed.tool_calls,
                usage=parsed.usage.usage,
                has_cost=parsed.has_cost,
                status=status,
            )
        return self._ingest_session(
            source="cursor",
            external_id=parsed.external_id,
            cwd=parsed.cwd,
            git_branch=None,
            started_at=parsed.started_at,
            ended_at=parsed.ended_at,
            model=parsed.model or "cursor",
            events=events,
            tool_calls=parsed.tool_calls,
            usage=parsed.usage.usage,
            has_cost=parsed.has_cost,
            status=status,
        )

    def list_sessions(
        self,
        *,
        limit: int = 20,
        source: str | None = None,
    ) -> list[SessionSummary]:
        if source:
            rows = self._conn.execute(
                """
                SELECT * FROM runs
                WHERE source = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (source, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_summary(r) for r in rows]

    def load_session_by_external_id(self, external_id: str) -> SessionSummary | None:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE external_id = ?",
            (external_id,),
        ).fetchone()
        return _row_to_summary(row) if row else None

    def load_events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE run_id = ? ORDER BY seq",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

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
        usage: ObservedUsage,
        has_cost: bool | None = None,
        status: str = "completed",
        context_window: int | None = None,
        rate_limit_used_pct: float | None = None,
        rate_limit_window_min: int | None = None,
        rate_limit_resets_at: str | None = None,
        plan_type: str | None = None,
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
        seq_events = assign_seq(events)
        tool_by_id = {tc.tool_use_id: tc for tc in tool_calls}
        flat_rows = [
            _flatten_event(
                event, source=source, tool_by_id=tool_by_id, cwd=cwd, root=self.project_root
            )
            for event in seq_events
        ]

        observed = _observed_usage_from_events(seq_events) if usage.input_tokens == 0 else usage
        model = model or _dominant_model(seq_events) or source
        cost_flag = has_cost if has_cost is not None else source in _HAS_COST_SOURCES
        total_cost = 0.0
        if cost_flag:
            if observed.cost is not None:
                total_cost = observed.cost
            else:
                total_cost = estimate_cost(model, observed, overrides=self._pricing_overrides).total

        tool_call_count = sum(1 for e in flat_rows if e["type"] == "tool_call")
        tool_error_count = sum(1 for e in flat_rows if e.get("tool_is_error"))
        project = _project_name(cwd, self.project_root)
        git_commit = try_git_commit(self.project_root)
        branch = git_branch or try_git_branch(self.project_root)
        started = started_at or datetime.now(UTC).isoformat()
        has_timestamps = 1 if started_at else 0
        output_estimated = 1 if getattr(observed, "output_estimated", False) else 0
        peak_ctx = _peak_context_pct(seq_events, context_window)

        self._conn.execute(
            """
            INSERT INTO runs (
              run_id, source, external_id, cwd, project, model,
              git_branch, git_commit, started_at, ended_at, status,
              total_input_tokens, total_output_tokens, output_estimated,
              cache_read_tokens, cache_creation_tokens, reasoning_tokens,
              total_cost, has_cost, has_timestamps, context_window, peak_context_pct,
              rate_limit_used_pct, rate_limit_window_min, rate_limit_resets_at, plan_type,
              event_count, tool_call_count, tool_error_count, waste_tokens
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                run_id,
                source,
                external_id,
                cwd,
                project,
                model,
                branch,
                git_commit,
                started,
                ended_at,
                status,
                observed.input_tokens,
                observed.output_tokens,
                output_estimated,
                observed.cache_read_tokens,
                observed.cache_creation_tokens,
                observed.reasoning_tokens,
                total_cost,
                1 if cost_flag else 0,
                has_timestamps,
                context_window,
                peak_ctx,
                rate_limit_used_pct,
                rate_limit_window_min,
                rate_limit_resets_at,
                plan_type,
                len(flat_rows),
                tool_call_count,
                tool_error_count,
            ),
        )

        for row in flat_rows:
            self._conn.execute(
                """
                INSERT INTO events (
                  run_id, seq, type, role, model, text_hash, text_inline,
                  tool_name, tool_norm_name, tool_is_error, path_rel,
                  input_tokens, output_tokens, input_estimated, output_estimated,
                  cache_read_tokens, cache_creation_tokens, context_tokens_after,
                  duration_ms, ts, agent_id, agent_lane
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    row["seq"],
                    row["type"],
                    row.get("role"),
                    row.get("model"),
                    row.get("text_hash"),
                    row.get("text_inline"),
                    row.get("tool_name"),
                    row.get("tool_norm_name"),
                    row.get("tool_is_error", 0),
                    row.get("path_rel"),
                    row.get("input_tokens"),
                    row.get("output_tokens"),
                    row.get("input_estimated", 0),
                    row.get("output_estimated", 0),
                    row.get("cache_read_tokens"),
                    row.get("cache_creation_tokens"),
                    row.get("context_tokens_after"),
                    row.get("duration_ms"),
                    row.get("ts"),
                    row.get("agent_id"),
                    row.get("agent_lane"),
                ),
            )

        self._write_event_fts(run_id, flat_rows)
        self._persist_data_quality(
            run_id,
            flat_rows=flat_rows,
            observed=observed,
            cost_flag=cost_flag,
            has_timestamps=bool(has_timestamps),
        )
        self._conn.commit()

        from cairn.ingest.backfill import backfill_run

        backfill_run(self, run_id)

        return IngestResult(
            external_id=external_id,
            run_id=run_id,
            inserted=True,
            event_count=len(flat_rows),
        )

    def _replace_session(
        self,
        *,
        run_id: str,
        source: str,
        external_id: str,
        cwd: str | None,
        git_branch: str | None,
        started_at: str | None,
        ended_at: str | None,
        model: str | None,
        events: list[dict[str, Any]],
        tool_calls: list[ToolCallDraft],
        usage: ObservedUsage,
        has_cost: bool | None = None,
        status: str = "completed",
        context_window: int | None = None,
        rate_limit_used_pct: float | None = None,
        rate_limit_window_min: int | None = None,
        rate_limit_resets_at: str | None = None,
        plan_type: str | None = None,
    ) -> IngestResult:
        """Replace an existing run's events + rollups (live Cursor refresh)."""
        self._conn.execute(
            "DELETE FROM context_regions WHERE event_id IN "
            "(SELECT event_id FROM events WHERE run_id = ?)",
            (run_id,),
        )
        self._conn.execute("DELETE FROM events WHERE run_id = ?", (run_id,))
        self._conn.execute("DELETE FROM fingerprints WHERE run_id = ?", (run_id,))
        self._conn.execute("DELETE FROM outcomes WHERE run_id = ?", (run_id,))
        self._conn.execute("DELETE FROM data_quality WHERE run_id = ?", (run_id,))

        seq_events = assign_seq(events)
        tool_by_id = {tc.tool_use_id: tc for tc in tool_calls}
        flat_rows = [
            _flatten_event(
                event, source=source, tool_by_id=tool_by_id, cwd=cwd, root=self.project_root
            )
            for event in seq_events
        ]
        observed = _observed_usage_from_events(seq_events) if usage.input_tokens == 0 else usage
        model = model or _dominant_model(seq_events) or source
        cost_flag = has_cost if has_cost is not None else source in _HAS_COST_SOURCES
        total_cost = 0.0
        if cost_flag:
            if observed.cost is not None:
                total_cost = observed.cost
            else:
                total_cost = estimate_cost(model, observed, overrides=self._pricing_overrides).total
        tool_call_count = sum(1 for e in flat_rows if e["type"] == "tool_call")
        tool_error_count = sum(1 for e in flat_rows if e.get("tool_is_error"))
        started = started_at or datetime.now(UTC).isoformat()
        has_timestamps = 1 if started_at else 0
        output_estimated = 1 if getattr(observed, "output_estimated", False) else 0
        peak_ctx = _peak_context_pct(seq_events, context_window)

        self._conn.execute(
            """
            UPDATE runs SET
              cwd = ?, started_at = ?, ended_at = ?, status = ?,
              total_input_tokens = ?, total_output_tokens = ?, output_estimated = ?,
              cache_read_tokens = ?, cache_creation_tokens = ?, reasoning_tokens = ?,
              total_cost = ?, has_cost = ?, has_timestamps = ?, context_window = ?,
              peak_context_pct = ?, rate_limit_used_pct = ?, rate_limit_window_min = ?,
              rate_limit_resets_at = ?, plan_type = ?, event_count = ?,
              tool_call_count = ?, tool_error_count = ?, waste_tokens = 0
            WHERE run_id = ?
            """,
            (
                cwd,
                started,
                ended_at,
                status,
                observed.input_tokens,
                observed.output_tokens,
                output_estimated,
                observed.cache_read_tokens,
                observed.cache_creation_tokens,
                observed.reasoning_tokens,
                total_cost,
                1 if cost_flag else 0,
                has_timestamps,
                context_window,
                peak_ctx,
                rate_limit_used_pct,
                rate_limit_window_min,
                rate_limit_resets_at,
                plan_type,
                len(flat_rows),
                tool_call_count,
                tool_error_count,
                run_id,
            ),
        )

        for row in flat_rows:
            self._conn.execute(
                """
                INSERT INTO events (
                  run_id, seq, type, role, model, text_hash, text_inline,
                  tool_name, tool_norm_name, tool_is_error, path_rel,
                  input_tokens, output_tokens, input_estimated, output_estimated,
                  cache_read_tokens, cache_creation_tokens, context_tokens_after,
                  duration_ms, ts, agent_id, agent_lane
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    row["seq"],
                    row["type"],
                    row.get("role"),
                    row.get("model"),
                    row.get("text_hash"),
                    row.get("text_inline"),
                    row.get("tool_name"),
                    row.get("tool_norm_name"),
                    row.get("tool_is_error", 0),
                    row.get("path_rel"),
                    row.get("input_tokens"),
                    row.get("output_tokens"),
                    row.get("input_estimated", 0),
                    row.get("output_estimated", 0),
                    row.get("cache_read_tokens"),
                    row.get("cache_creation_tokens"),
                    row.get("context_tokens_after"),
                    row.get("duration_ms"),
                    row.get("ts"),
                    row.get("agent_id"),
                    row.get("agent_lane"),
                ),
            )

        self._write_event_fts(run_id, flat_rows)
        self._persist_data_quality(
            run_id,
            flat_rows=flat_rows,
            observed=observed,
            cost_flag=cost_flag,
            has_timestamps=bool(has_timestamps),
        )
        self._conn.commit()

        from cairn.ingest.backfill import backfill_run

        backfill_run(self, run_id)

        return IngestResult(
            external_id=external_id,
            run_id=run_id,
            inserted=False,
            refreshed=True,
            event_count=len(flat_rows),
        )

    def write_context_regions(self, run_id: str, regions: list[dict[str, Any]]) -> None:
        """Insert Pillar-1 context-region rows for one assistant event turn.

        Each row: ``{event_id, region, tokens, cost, content_hash, first_turn,
        last_seen_turn, still_in_window}``. Phase A plumbing — safe to call with
        an empty list (the profiler is Phase B).
        """
        if not regions:
            return
        with self._conn:
            for row in regions:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO context_regions (
                      event_id, region, tokens, cost, content_hash,
                      first_turn, last_seen_turn, still_in_window
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("event_id"),
                        row.get("region"),
                        int(row.get("tokens") or 0),
                        float(row.get("cost") or 0.0),
                        row.get("content_hash"),
                        row.get("first_turn"),
                        row.get("last_seen_turn"),
                        int(bool(row.get("still_in_window"))),
                    ),
                )

    def _persist_data_quality(
        self,
        run_id: str,
        *,
        flat_rows: list[dict[str, Any]],
        observed: ObservedUsage,
        cost_flag: bool,
        has_timestamps: bool,
    ) -> None:
        dq = compute_data_quality(
            flat_rows=flat_rows,
            observed=observed,
            has_cost=cost_flag,
            has_timestamps=has_timestamps,
            cost_was_priced=cost_flag and observed.cost is None,
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO data_quality (
              run_id, pct_tokens_measured, pct_tokens_estimated,
              timestamps_present, cost_source, parser_version,
              dropped_events, notes_json, computed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                dq["pct_tokens_measured"],
                dq["pct_tokens_estimated"],
                dq["timestamps_present"],
                dq["cost_source"],
                dq["parser_version"] or PARSER_VERSION,
                dq["dropped_events"],
                dq["notes_json"],
                datetime.now(UTC).isoformat(),
            ),
        )

    def write_fingerprint(
        self,
        run_id: str,
        *,
        project: str | None,
        model: str | None,
        source: str | None,
        ts: str | None,
        vector: list[float],
        read_write_ratio: float | None = None,
        exploration_ratio: float | None = None,
        retry_rate: float | None = None,
        context_fill_traj: list[float] | None = None,
        turn_count: int | None = None,
        tool_entropy: float | None = None,
        week: str | None = None,
    ) -> None:
        """Insert a Pillar-2 behavioral fingerprint (Phase A plumbing)."""
        import json as _json

        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO fingerprints (
                  run_id, project, model, source, ts, vector_json,
                  read_write_ratio, exploration_ratio, retry_rate,
                  context_fill_traj_json, turn_count, tool_entropy, week
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    project,
                    model,
                    source,
                    ts,
                    _json.dumps(list(vector)),
                    read_write_ratio,
                    exploration_ratio,
                    retry_rate,
                    _json.dumps(context_fill_traj) if context_fill_traj is not None else None,
                    turn_count,
                    tool_entropy,
                    week,
                ),
            )

    def write_fingerprint_baseline(
        self,
        *,
        project: str,
        model: str,
        week: str,
        mean_vector: list[float],
        cov_inv: list[list[float]],
        n: int,
    ) -> None:
        """Insert/update a Pillar-2 weekly baseline (Phase A plumbing)."""
        import json as _json

        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO fingerprint_baselines (
                  project, model, week, mean_vector_json, cov_inv_json, n
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project,
                    model,
                    week,
                    _json.dumps(list(mean_vector)),
                    _json.dumps(cov_inv),
                    int(n),
                ),
            )

    def write_outcome(
        self,
        run_id: str,
        *,
        commit_sha: str | None = None,
        commit_landed: bool = False,
        files_changed: list[str] | None = None,
        tests_run: int | None = None,
        tests_passed: int | None = None,
        tests_failed: int | None = None,
        build_status: str | None = None,
        quality_score: float | None = None,
        cost_per_success: float | None = None,
        captured_at: str | None = None,
    ) -> None:
        """Insert a Pillar-3 outcome row (Phase A plumbing; Phase B fills it)."""
        import json as _json

        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO outcomes (
                  run_id, commit_sha, commit_landed, files_changed_json,
                  tests_run, tests_passed, tests_failed, build_status,
                  quality_score, cost_per_success, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    commit_sha,
                    1 if commit_landed else 0,
                    _json.dumps(files_changed or []),
                    tests_run,
                    tests_passed,
                    tests_failed,
                    build_status,
                    quality_score,
                    cost_per_success,
                    captured_at,
                ),
            )

    def _write_event_fts(self, run_id: str, rows: list[dict[str, Any]]) -> None:
        if not FTS_AVAILABLE:
            return
        fts_rows = []
        for row in rows:
            text = row.get("text_inline")
            if text:
                fts_rows.append((run_id, row["seq"], str(text)[:8192]))
        if fts_rows:
            with contextlib.suppress(sqlite3.OperationalError):
                self._conn.executemany(
                    "INSERT INTO events_fts (run_id, seq, text_inline) VALUES (?, ?, ?)",
                    fts_rows,
                )


def _row_to_summary(row: sqlite3.Row) -> SessionSummary:
    return SessionSummary(
        run_id=str(row["run_id"]),
        external_id=str(row["external_id"] or ""),
        source=str(row["source"]),
        project=row["project"],
        cwd=row["cwd"],
        git_branch=row["git_branch"],
        git_commit=row["git_commit"],
        started_at=str(row["started_at"] or ""),
        ended_at=row["ended_at"],
        status=str(row["status"]),
        model=row["model"],
        total_input_tokens=int(row["total_input_tokens"] or 0),
        total_output_tokens=int(row["total_output_tokens"] or 0),
        total_cost=float(row["total_cost"] or 0),
        has_cost=bool(row["has_cost"]),
        waste_tokens=int(row["waste_tokens"] or 0),
        event_count=int(row["event_count"] or 0),
        tool_call_count=int(row["tool_call_count"] or 0),
        tool_error_count=int(row["tool_error_count"] or 0),
    )


def _project_name(cwd: str | None, root: Path) -> str:
    if cwd:
        p = Path(cwd).resolve()
        if p.name:
            return p.name
    return root.name


def _dominant_model(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        if event.get("type") == "assistant_message":
            model = event.get("model")
            if isinstance(model, str) and model:
                return model
    return None


def _observed_usage_from_events(events: list[dict[str, Any]]) -> ObservedUsage:
    usage = ObservedUsage()
    for event in events:
        raw = event.get("usage")
        if isinstance(raw, dict):
            usage.add(extract_usage_dict(raw))
    return usage


def _normalize_tool_name(name: str, source: str) -> str:
    return normalize_tool_name(name, source=source)


def _truncate_inline(text: str | None) -> str | None:
    if not text:
        return None
    if len(text) <= _TEXT_INLINE_MAX:
        return text
    return text[:_TEXT_INLINE_MAX]


def _event_text(event: dict[str, Any]) -> tuple[str | None, str | None]:
    for key in ("text_inline", "text"):
        val = event.get(key)
        if isinstance(val, str) and val:
            return event.get("text_hash"), _truncate_inline(val)
    for key in ("args_inline", "result_inline"):
        val = event.get(key)
        if isinstance(val, str) and val:
            return event.get("args_hash") or event.get("result_hash"), _truncate_inline(val)
        if isinstance(val, dict):
            import json as _json

            s = _json.dumps(val, sort_keys=True)[:_TEXT_INLINE_MAX]
            return event.get("args_hash"), s
    return event.get("text_hash") or event.get("args_hash"), None


def _flatten_event(
    event: dict[str, Any],
    *,
    source: str,
    tool_by_id: dict[str, ToolCallDraft],
    cwd: str | None,
    root: Path,
) -> dict[str, Any]:
    etype = str(event.get("type", "unknown"))
    role: str | None = None
    if etype == "user_prompt":
        role = "user"
    elif etype in ("assistant_message", "tool_call"):
        role = "assistant"
    elif etype == "tool_result":
        role = "tool"

    text_hash, text_inline = _event_text(event)
    tool_name = event.get("tool_name") or event.get("name")
    tool_norm: str | None = None
    path_rel = event.get("path_rel")
    tool_is_error = 1 if event.get("is_error") else 0

    if etype == "tool_call" and isinstance(tool_name, str):
        tool_norm = _normalize_tool_name(tool_name, source)
        draft = tool_by_id.get(str(event.get("tool_use_id", "")))
        if draft and draft.path_rel:
            path_rel = draft.path_rel
        elif not path_rel:
            path_rel = _path_from_tool_input(event, cwd, root)

    if etype == "tool_result":
        tool_use_id = str(event.get("tool_use_id", ""))
        draft = tool_by_id.get(tool_use_id)
        if draft:
            tool_name = draft.name
            tool_norm = _normalize_tool_name(draft.name, source)
            path_rel = path_rel or draft.path_rel

    if etype == "file_snapshot":
        path_rel = path_rel or event.get("path_rel")

    usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
    obs = extract_usage_dict(usage) if usage else ObservedUsage()

    input_tokens = obs.input_tokens or event.get("input_tokens")
    output_tokens = obs.output_tokens or event.get("output_tokens")
    input_estimated = 1 if (obs.input_estimated or event.get("input_estimated")) else 0
    output_estimated = 1 if (obs.output_estimated or event.get("output_estimated")) else 0

    return {
        "seq": int(event["seq"]),
        "type": etype,
        "role": role,
        "model": event.get("model"),
        "text_hash": text_hash,
        "text_inline": text_inline,
        "tool_name": tool_name,
        "tool_norm_name": tool_norm,
        "tool_is_error": tool_is_error,
        "path_rel": path_rel,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_estimated": input_estimated,
        "output_estimated": output_estimated,
        "cache_read_tokens": obs.cache_read_tokens or event.get("cache_read_tokens"),
        "cache_creation_tokens": obs.cache_creation_tokens or event.get("cache_creation_tokens"),
        "context_tokens_after": event.get("context_tokens_after"),
        "duration_ms": event.get("duration_ms"),
        "ts": event.get("ts") or event.get("timestamp"),
        "agent_id": event.get("agent_id"),
        "agent_lane": event.get("agent_lane"),
    }


def _peak_context_pct(events: list[dict[str, Any]], context_window: int | None) -> float | None:
    peak = 0
    for event in events:
        ctx = event.get("context_tokens_after")
        if isinstance(ctx, int) and ctx > 0:
            peak = max(peak, ctx)
    if peak <= 0:
        return None
    window = context_window or 200_000
    if window <= 0:
        return None
    return round(peak / window * 100, 1)


def _path_from_tool_input(event: dict[str, Any], cwd: str | None, root: Path) -> str | None:
    args = event.get("args_inline") or event.get("tool_input") or {}
    if not isinstance(args, dict):
        return None
    for key in ("file_path", "path", "target_file"):
        val = args.get(key)
        if isinstance(val, str) and val:
            return path_rel_to_repo(
                root, val if Path(val).is_absolute() else str((Path(cwd or root) / val).resolve())
            )
    return None
