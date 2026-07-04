"""Pillar 5 — MCP tool implementations (Part 14 + §2.7F)."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from cairn.ingest.project_paths import resolve_git_root

_READ_NORMS = frozenset({"read", "search"})
_WORD_RE = re.compile(r"[A-Za-z0-9_./-]+")
_DEFAULT_SIMILARITY = 0.9
_AGING_DAYS = 30


@dataclass
class ToolsContext:
    conn: sqlite3.Connection
    project_root: Path
    project_name: str
    similarity_threshold: float = _DEFAULT_SIMILARITY

    def close(self) -> None:
        self.conn.close()


def open_context(start_cwd: Path, *, similarity_threshold: float | None = None) -> ToolsContext:
    """Open the ledger for the project that contains *start_cwd*."""
    root = resolve_git_root(start_cwd) or start_cwd.resolve()
    db_path = root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        # Fall back to a fresh empty ledger so tools return empty/null cleanly.
        conn = _open_fresh(root)
    else:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return ToolsContext(
        conn=conn,
        project_root=root,
        project_name=root.name,
        similarity_threshold=similarity_threshold or _DEFAULT_SIMILARITY,
    )


def _open_fresh(root: Path) -> sqlite3.Connection:
    import tempfile

    tmp = Path(tempfile.gettempdir()) / "cairn_mcp_empty.db"
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(str(tmp))
    from cairn.ledger.schema import migrate

    migrate(conn)
    return conn


# ---------------------------------------------------------------------------
# Tool descriptors
# ---------------------------------------------------------------------------


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "cairn_have_i_read",
        "description": (
            "Have I already read this file? Dedups trivially-changed re-reads "
            "via content similarity."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Repo-relative or absolute file path"},
                "within_session": {"type": "boolean", "description": "Restrict to the latest run"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "cairn_what_do_i_know_about",
        "description": "Full-text search over past events for a topic; optional LLM synthesis.",
        "inputSchema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
    {
        "name": "cairn_my_waste_patterns",
        "description": "Top 3 recurring waste patterns for a project (or all).",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
        },
    },
    {
        "name": "cairn_project_primer",
        "description": (
            "Compressed, always-current System Primer for a project "
            "(waste, files, fingerprint, rules)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}, "task": {"type": "string"}},
            "required": ["project"],
        },
    },
    {
        "name": "cairn_active_rules",
        "description": "List currently-applied managed-block rules for a project.",
        "inputSchema": {
            "type": "object",
            "properties": {"project": {"type": "string"}},
        },
    },
    {
        "name": "cairn_log_outcome",
        "description": "Agent self-reports an outcome (best-effort signal for quality score).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "success": {"type": "boolean"},
            },
            "required": ["summary"],
        },
    },
    {
        "name": "cairn_spend_today",
        "description": "Today's tokens/cost + rate-limit status. Multi-agent aggregate.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cairn_replay_last",
        "description": "Last run's waste/findings — 'what went wrong last time?' (read-only).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cairn_diagnose_last",
        "description": "Why the last session struggled and one suggested fix.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cairn_expected_cost",
        "description": "Difficulty-aware token/cost budget before starting a task.",
        "inputSchema": {
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"],
        },
    },
    {
        "name": "cairn_known_pitfalls",
        "description": "Files that historically seed error cascades.",
        "inputSchema": {
            "type": "object",
            "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
        },
    },
    {
        "name": "cairn_recall_episode",
        "description": "Past winning approach for a similar task.",
        "inputSchema": {
            "type": "object",
            "properties": {"task": {"type": "string"}},
            "required": ["task"],
        },
    },
    {
        "name": "cairn_should_i_stop",
        "description": (
            "Mid-session loop guard: should the agent stop repeating failing tool calls?"
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def list_tools() -> list[dict[str, Any]]:
    return [
        {"name": t["name"], "description": t["description"], "schema": t["inputSchema"]}
        for t in TOOL_SCHEMAS
    ]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def call_tool(ctx: ToolsContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
    dispatch = {
        "cairn_have_i_read": _have_i_read,
        "cairn_what_do_i_know_about": _what_do_i_know,
        "cairn_my_waste_patterns": _my_waste_patterns,
        "cairn_project_primer": _project_primer,
        "cairn_active_rules": _active_rules,
        "cairn_log_outcome": _log_outcome,
        "cairn_spend_today": _spend_today,
        "cairn_replay_last": _replay_last,
        "cairn_diagnose_last": _diagnose_last,
        "cairn_expected_cost": _expected_cost,
        "cairn_known_pitfalls": _known_pitfalls,
        "cairn_recall_episode": _recall_episode,
        "cairn_should_i_stop": _should_i_stop,
    }
    fn = dispatch.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(ctx, args)
    except Exception as exc:  # never crash the server
        return {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def _have_i_read(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    path = str(args.get("path") or "")
    within_session = bool(args.get("within_session"))
    if not path:
        return {"read": False, "reason": "no path provided"}
    rel = _rel_path(ctx, path)

    sql = (
        "SELECT e.seq, e.ts, e.text_inline, r.started_at, r.run_id "
        "FROM events e JOIN runs r ON e.run_id = r.run_id "
        "WHERE e.type = 'tool_call' AND e.tool_norm_name IN ('read','search') "
        "AND e.path_rel = ? ORDER BY e.seq"
    )
    params: list[Any] = [rel]
    if within_session:
        last = ctx.conn.execute(
            "SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if last is None:
            return {"read": False, "reason": "no runs in ledger", "path": rel}
        sql += " AND e.run_id = ?"
        params.append(last["run_id"])
    rows = ctx.conn.execute(sql, params).fetchall()
    if not rows:
        # Try a suffix match in case the caller used an absolute path.
        rows = ctx.conn.execute(
            sql.replace("e.path_rel = ?", "e.path_rel LIKE ?"),
            [f"%{rel}"] + params[1:],
        ).fetchall()
    if not rows:
        return {"read": False, "path": rel, "times": 0}

    # Dedup trivially-changed re-reads via Jaccard similarity.
    groups = _dedup_reads(rows, ctx.similarity_threshold)
    distinct = len(groups)
    last_row = rows[-1]
    last_turn = int(last_row["seq"] or 0)
    ago = _ago(last_row["ts"])
    return {
        "read": True,
        "path": rel,
        "times": distinct,
        "last": {"turn": last_turn, "ts": last_row["ts"], "ago": ago},
        "note": "trivially-changed re-reads deduplicated" if distinct < len(rows) else None,
    }


def _what_do_i_know(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    topic = str(args.get("topic") or "")
    if not topic:
        return {"snippets": [], "synthesis": None, "reason": "no topic provided"}
    snippets = _fts_search(ctx, topic, limit=8)
    synthesis = _optional_synthesize(topic, snippets)
    return {"topic": topic, "snippets": snippets, "synthesis": synthesis}


def _my_waste_patterns(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    project = args.get("project")
    where = ""
    params: list[Any] = []
    if project:
        where = "WHERE r.project = ?"
        params = [str(project)]
    rows = ctx.conn.execute(
        f"""
        SELECT e.waste_category AS cat, COUNT(*) AS n, SUM(e.waste_tokens) AS tokens
        FROM events e JOIN runs r ON e.run_id = r.run_id
        {where}
        GROUP BY e.waste_category HAVING e.waste_category IS NOT NULL
        ORDER BY n DESC LIMIT 3
        """,
        params,
    ).fetchall()
    patterns = [
        {"pattern": r["cat"], "count": int(r["n"]), "tokens": int(r["tokens"] or 0)} for r in rows
    ]
    if not patterns:
        return {"patterns": [], "note": "no waste patterns recorded yet"}
    return {"patterns": patterns}


def _project_primer(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    project = str(args.get("project") or ctx.project_name)
    task = str(args.get("task") or "")
    waste = _my_waste_patterns(ctx, {"project": project}).get("patterns", [])
    recurring = _recurring_files(ctx, project, limit=5)
    baseline = _fingerprint_baseline_summary(ctx, project)
    rules = _active_rules(ctx, {"project": project}).get("rules", [])
    pitfalls = _known_pitfalls(ctx, {}).get("pitfalls", [])[:3]

    facts: list[dict[str, Any]] = []
    for w in waste:
        facts.append(
            {
                "fact": f"recurring waste: {w['pattern']} ({w['count']}x)",
                "source": "waste",
                "age_days": None,
            }
        )
    for f in recurring:
        facts.append(
            {
                "fact": f"hotspot file: {f['path']} ({f['touches']} touches)",
                "source": "files",
                "age_days": None,
            }
        )
    if baseline:
        facts.append(
            {
                "fact": (
                    f"baseline behavior: r/w={baseline.get('read_write_ratio')}, "
                    f"entropy={baseline.get('tool_entropy')}"
                ),
                "source": "fingerprint",
                "age_days": None,
            }
        )
    for rl in rules:
        facts.append(
            {
                "fact": f"managed rule: {rl['block_key']} in {rl['target_file']}",
                "source": "rule",
                "age_days": rl.get("age_days"),
            }
        )
    for p in pitfalls:
        facts.append(
            {
                "fact": f"historical cascade hotspot: {p.get('path')}",
                "source": "pitfall",
                "age_days": None,
            }
        )

    # Aging-fact verification flag.
    date.today()
    verified: list[dict[str, Any]] = []
    for f in facts:
        age = f.get("age_days")
        if age is not None and age > _AGING_DAYS:
            f["verify_before_relying"] = True
        verified.append(f)

    cost_warning: str | None = None
    if task:
        forecast = _expected_cost(ctx, {"task": task})
        exp = forecast.get("expected_tokens")
        stdev = forecast.get("stdev")
        if exp is not None and stdev is not None:
            p95 = float(exp) + 1.645 * float(stdev)
            est = float(forecast.get("estimated_tokens") or len(task) * 4)
            if est > p95:
                cost_warning = (
                    f"Expected cost for this task shape is high vs baseline "
                    f"(p95 band ≈ {p95:.0f} tokens for {forecast.get('difficulty_bucket')} tasks)."
                )

    primer = (
        f"# {project} — System Primer\n\n"
        f"Waste patterns: {', '.join(w['pattern'] for w in waste) or 'none yet'}.\n"
        f"Hotspot files: {', '.join(f['path'] for f in recurring) or 'none yet'}.\n"
        f"Active managed rules: {len(rules)}.\n"
    )
    if pitfalls:
        primer += f"Known cascade hotspots: {', '.join(p['path'] for p in pitfalls)}.\n"
    if cost_warning:
        primer += f"\n{cost_warning}\n"
    return {
        "project": project,
        "primer": primer,
        "waste_patterns": waste,
        "recurring_files": recurring,
        "fingerprint_baseline": baseline,
        "active_rules": rules,
        "known_pitfalls": pitfalls,
        "cost_warning": cost_warning,
        "facts": verified,
        "data_notes": ["facts older than 30 days carry verify_before_relying"],
    }


def _active_rules(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    # The ledger is already project-scoped (one .cairn/ledger.db per project),
    # so all applied managed rules belong to this project.
    rows = ctx.conn.execute(
        "SELECT opt_id, target_file, block_key, kind, applied_at "
        "FROM optimizations WHERE status = 'applied' ORDER BY applied_at DESC"
    ).fetchall()
    today = date.today()
    rules = []
    for r in rows:
        age = _age_days(r["applied_at"], today)
        rules.append(
            {
                "opt_id": r["opt_id"],
                "target_file": r["target_file"],
                "block_key": r["block_key"],
                "kind": r["kind"],
                "applied_at": r["applied_at"],
                "age_days": age,
            }
        )
    if not rules:
        return {"rules": [], "note": "no applied managed rules"}
    return {"rules": rules}


def _log_outcome(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    summary = str(args.get("summary") or "")
    success = args.get("success")
    # Best-effort: append to a side jsonl log under .cairn/.
    log_path = ctx.project_root / ".cairn" / "outcome_self_reports.jsonl"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "ts": datetime.now().isoformat(),
                        "summary": summary,
                        "success": success,
                        "project": ctx.project_name,
                    }
                )
                + "\n"
            )
    except OSError:
        pass
    return {"ok": True, "note": "best-effort self-report recorded"}


def _spend_today(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    today = date.today().isoformat()
    rows = ctx.conn.execute(
        """
        SELECT source, SUM(total_input_tokens) AS inp, SUM(total_output_tokens) AS outp,
               SUM(total_cost) AS cost, MAX(rate_limit_used_pct) AS rl,
               MAX(rate_limit_resets_at) AS resets
        FROM runs WHERE substr(started_at, 1, 10) = ?
        GROUP BY source
        """,
        (today,),
    ).fetchall()
    if not rows:
        return {"today": today, "sources": [], "note": "no sessions today"}
    sources = [
        {
            "source": r["source"],
            "input_tokens": int(r["inp"] or 0),
            "output_tokens": int(r["outp"] or 0),
            "cost_usd": float(r["cost"] or 0.0),
            "rate_limit_used_pct": r["rl"],
            "rate_limit_resets_at": r["resets"],
        }
        for r in rows
    ]
    total_cost = sum(s["cost_usd"] for s in sources)
    total_in = sum(s["input_tokens"] for s in sources)
    total_out = sum(s["output_tokens"] for s in sources)
    return {
        "today": today,
        "sources": sources,
        "total": {
            "input_tokens": total_in,
            "output_tokens": total_out,
            "cost_usd": round(total_cost, 4),
        },
    }


def _replay_last(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    last = ctx.conn.execute("SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
    if last is None:
        return {"run_id": None, "waste": [], "findings": [], "note": "no runs in ledger"}
    run_id = str(last["run_id"])
    waste_rows = ctx.conn.execute(
        "SELECT waste_category, COUNT(*) AS n, SUM(waste_tokens) AS tokens "
        "FROM events WHERE run_id = ? AND waste_category IS NOT NULL GROUP BY waste_category",
        (run_id,),
    ).fetchall()
    waste = [
        {"category": r["waste_category"], "count": int(r["n"]), "tokens": int(r["tokens"] or 0)}
        for r in waste_rows
    ]
    # Best-effort profile findings (decompose + detect).
    findings: list[dict[str, Any]] = []
    try:
        from cairn.ingest.writer import CaptureWriter
        from cairn.profile.compute import profile_run

        writer = CaptureWriter(ctx.project_root)
        try:
            payload = profile_run(writer, run_id)
            findings = payload.get("findings") or []
        finally:
            writer.close()
    except Exception:
        pass
    return {"run_id": run_id, "waste": waste, "findings": findings}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rel_path(ctx: ToolsContext, path: str) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(ctx.project_root).as_posix()
        except ValueError:
            return path
    return path


def _dedup_reads(rows: list[sqlite3.Row], threshold: float) -> list[list[sqlite3.Row]]:
    """Group read rows by Jaccard similarity > threshold into distinct groups."""
    groups: list[list[sqlite3.Row]] = []
    sets: list[set[str]] = []
    for r in rows:
        s = _token_set(str(r["text_inline"] or ""))
        placed = False
        for i, gset in enumerate(sets):
            if not s and not gset:
                groups[i].append(r)
                placed = True
                break
            union = s | gset
            if union and len(s & gset) / len(union) > threshold:
                groups[i].append(r)
                sets[i] = gset | s
                placed = True
                break
        if not placed:
            groups.append([r])
            sets.append(s)
    return groups


def _token_set(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD_RE.finditer(text)}


def _ago(ts: str | None) -> str | None:
    if not ts:
        return None
    try:
        then = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    delta = datetime.now(then.tzinfo) - then
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "just now"
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _age_days(ts: str | None, today: date) -> int | None:
    if not ts:
        return None
    try:
        d = date.fromisoformat(str(ts)[:10])
    except (ValueError, TypeError):
        return None
    return (today - d).days


def _fts_search(ctx: ToolsContext, topic: str, *, limit: int = 8) -> list[dict[str, Any]]:
    from cairn.ledger.schema import FTS_AVAILABLE

    if not FTS_AVAILABLE:
        # Fallback: LIKE search on text_inline.
        rows = ctx.conn.execute(
            "SELECT run_id, seq, text_inline FROM events "
            "WHERE text_inline LIKE ? ORDER BY seq DESC LIMIT ?",
            (f"%{topic}%", limit),
        ).fetchall()
        return [
            {"run_id": r["run_id"], "seq": r["seq"], "snippet": (r["text_inline"] or "")[:200]}
            for r in rows
        ]
    try:
        rows = ctx.conn.execute(
            "SELECT run_id, seq, snippet(events_fts, 2, '[', ']', '...', 20) AS snip "
            "FROM events_fts WHERE events_fts MATCH ? ORDER BY rank LIMIT ?",
            (topic, limit),
        ).fetchall()
        return [{"run_id": r["run_id"], "seq": r["seq"], "snippet": r["snip"]} for r in rows]
    except sqlite3.OperationalError:
        rows = ctx.conn.execute(
            "SELECT run_id, seq, text_inline FROM events "
            "WHERE text_inline LIKE ? ORDER BY seq DESC LIMIT ?",
            (f"%{topic}%", limit),
        ).fetchall()
        return [
            {"run_id": r["run_id"], "seq": r["seq"], "snippet": (r["text_inline"] or "")[:200]}
            for r in rows
        ]


def _optional_synthesize(topic: str, snippets: list[dict[str, Any]]) -> str | None:
    """Optional LLM synthesis. httpx is import-guarded; never required."""
    if not snippets:
        return None
    try:
        import httpx
    except ImportError:
        # Fallback: stitch top snippets into one paragraph.
        tops = "; ".join(s["snippet"][:120] for s in snippets[:3])
        return f"What I know about {topic}: {tops}." if tops else None
    # An LLM call would go here; we deliberately do not require network in tests.
    del httpx
    tops = "; ".join(s["snippet"][:120] for s in snippets[:3])
    return f"What I know about {topic}: {tops}." if tops else None


def _recurring_files(ctx: ToolsContext, project: str, *, limit: int = 5) -> list[dict[str, Any]]:
    rows = ctx.conn.execute(
        """
        SELECT e.path_rel AS path, COUNT(*) AS n
        FROM events e JOIN runs r ON e.run_id = r.run_id
        WHERE e.path_rel IS NOT NULL AND r.project = ?
        GROUP BY e.path_rel ORDER BY n DESC LIMIT ?
        """,
        (project, limit),
    ).fetchall()
    return [{"path": r["path"], "touches": int(r["n"])} for r in rows]


def _fingerprint_baseline_summary(ctx: ToolsContext, project: str) -> dict[str, Any] | None:
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


def _diagnose_last(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    row = ctx.conn.execute("SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
    if row is None:
        return {"error": "no sessions"}
    run_id = str(row["run_id"])
    diag = ctx.conn.execute("SELECT * FROM diagnostics WHERE run_id = ?", (run_id,)).fetchone()
    if diag is None:
        return {
            "run_id": run_id,
            "message": "diagnostics not computed yet; run cairn sync --backfill",
        }
    return {
        "run_id": run_id,
        "outcome_label": diag["outcome_label"],
        "primary_category": diag["primary_category"],
        "failure_signature": diag["failure_signature"],
        "ideal_path_savings_tokens": diag["ideal_path_savings_tokens"],
        "suggested_fix": "Review failure origin in session autopsy",
    }


def _expected_cost(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    task = str(args.get("task") or "")
    from cairn.metrics.difficulty import estimate_difficulty

    fake_run = {"total_input_tokens": len(task) * 2, "total_output_tokens": 0}
    fake_events = [{"type": "user_prompt", "text_inline": task}] if task else []
    score = estimate_difficulty(fake_run, fake_events)
    exp = ctx.conn.execute(
        """
        SELECT mean, stdev, n FROM expectation_baselines
        WHERE model = 'unknown' AND difficulty_bucket = ? AND metric = 'total_tokens'
        """,
        (score.bucket,),
    ).fetchone()
    estimated_tokens = float(len(task) * 4) if task else None
    if exp and int(exp["n"] or 0) >= 5 and exp["mean"]:
        return {
            "difficulty_bucket": score.bucket,
            "expected_tokens": float(exp["mean"]),
            "stdev": float(exp["stdev"] or 0),
            "n": int(exp["n"]),
            "estimated_tokens": estimated_tokens,
            "data_notes": [],
        }
    return {
        "difficulty_bucket": score.bucket,
        "expected_tokens": None,
        "estimated_tokens": estimated_tokens,
        "data_notes": ["insufficient baseline data for budget forecast"],
    }


def _known_pitfalls(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    paths = args.get("paths") or []
    clauses = ""
    params: list[Any] = []
    if paths:
        clauses = "AND e.path_rel IN ({})".format(",".join("?" * len(paths)))
        params = list(paths)
    rows = ctx.conn.execute(
        f"""
        SELECT e.path_rel, COUNT(*) AS n
        FROM diagnostics d
        JOIN events e ON e.event_id = d.cascade_root_event_id
        WHERE e.path_rel IS NOT NULL {clauses}
        GROUP BY e.path_rel ORDER BY n DESC LIMIT 10
        """,
        params,
    ).fetchall()
    return {"pitfalls": [{"path": r["path_rel"], "cascade_count": int(r["n"])} for r in rows]}


def _recall_episode(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    from cairn.optimize.memory import recall_episode

    task = str(args.get("task") or "")
    ep = recall_episode(ctx.conn, task)
    if ep is None:
        return {"episode": None, "data_notes": ["no matching episode"]}
    return {"episode": ep}


def _should_i_stop(ctx: ToolsContext, args: dict[str, Any]) -> dict[str, Any]:
    """Analyze the latest session tail for loop/cascade patterns."""
    from cairn.diagnose.should_stop import should_stop_verdict

    last = ctx.conn.execute("SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
    if last is None:
        return {"should_stop": False, "reason": "insufficient signal", "suggestion": None}
    run_id = str(last["run_id"])
    rows = ctx.conn.execute(
        "SELECT * FROM events WHERE run_id = ? ORDER BY seq",
        (run_id,),
    ).fetchall()
    events = [dict(r) for r in rows]
    verdict = should_stop_verdict(events)
    verdict["run_id"] = run_id
    return verdict
