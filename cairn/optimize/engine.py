"""The optimize loop: evidence -> proposals -> diff -> apply -> measure."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cairn.insights.engine import evaluate, render_feed
from cairn.ledger.ledger import Ledger
from cairn.optimize.apply import Entry, ProposalRecord, apply_proposals, preview_diff
from cairn.optimize.evidence import build_evidence
from cairn.optimize.targets import observed_sources_from_ledger


def optimize(root: Path, args: argparse.Namespace) -> int:
    db = root / ".cairn" / "ledger.db"
    if not db.is_file():
        print("No ledger yet. Run `cairn sync` first.")
        return 0

    days = int(getattr(args, "days", 14) or 14)
    use_llm = bool(getattr(args, "llm", False))
    backend_override = getattr(args, "backend", None)
    want_json = bool(getattr(args, "json", False))
    auto = bool(getattr(args, "auto", False))
    do_apply = bool(getattr(args, "apply", False))
    force = bool(getattr(args, "force", False))

    ledger = Ledger(db)
    try:
        insights = evaluate(ledger, days=days)
        records = generate_proposals(ledger.connection, root, days=days)
        backend_used = "evidence"
        if use_llm and records:
            llm_records, backend_used = _reflect_records(ledger, root, days, backend_override)
            if llm_records:
                records = llm_records
        observed = observed_sources_from_ledger(root)
    finally:
        ledger.close()

    if want_json:
        print(json.dumps(_json_payload(insights, records), indent=2, default=str))
        return 0

    render_feed(insights)

    if not records:
        print("No optimization proposals — your instruction files look up to date.")
        return 0

    if auto:
        print(f"\n{len(records)} optimization suggestion(s) ready → cairn optimize")
        return 0

    diff = preview_diff(root, records)
    print(f"\n{len(records)} proposal(s) for AGENTS.md (backend: {backend_used}):\n")
    print(diff or "(no change)")

    if not do_apply and sys.stdin.isatty() and sys.stdout.isatty():
        do_apply = input("\nApply these changes? [y/N] ").strip().lower() == "y"

    if not do_apply:
        print("\nNothing written. Re-run with --apply to write these changes.")
        return 0

    result = apply_proposals(root, records, force=force, observed_sources=observed)
    if result.refused:
        print(f"\nRefused: {result.refused}")
        return 1
    print(f"\nApplied {result.applied} entr{'y' if result.applied == 1 else 'ies'} to AGENTS.md.")

    # Run the measured loop on every applied rule: update verdicts + bandit,
    # prune regressions, auto-revert. Best-effort; never blocks the apply.
    try:
        from cairn.optimize.impact import run_measurement

        summary = run_measurement(root)
        _print_measurement(summary)
    except Exception as exc:  # noqa: BLE001
        print(f"\nMeasurement skipped: {exc}", file=sys.stderr)
    return 0


def _print_measurement(summary: dict[str, Any]) -> None:
    verdicts = summary.get("verdicts", []) or []
    pruned = summary.get("pruned", []) or []
    if not verdicts and not pruned:
        return
    print("\nMeasurement:")
    for v in verdicts:
        ba = "-" if v.get("baseline") is None else f"{v['baseline']:g}"
        oa = "-" if v.get("outcome") is None else f"{v['outcome']:g}"
        print(
            f"  [{v['verdict']}] {v['block_key']}  {ba} -> {oa}  "
            f"(holdout {v.get('holdout_size', 0)}, P(improve) {v.get('p_improve', 0):.2f})"
        )
    if pruned:
        print(f"\nAuto-pruned {len(pruned)} regressed rule(s): {', '.join(pruned)}")


def _reflect_records(
    ledger: Ledger, root: Path, days: int, backend_override: str | None
) -> tuple[list[ProposalRecord] | None, str]:
    from cairn.optimize.apply import Entry, has_block, parse_block
    from cairn.optimize.reflector import ReflectorError, reflect, resolve_backend, resolve_evidence

    backend = resolve_backend(backend_override)
    if backend is None:
        print("No LLM backend found; using deterministic proposals.", file=sys.stderr)
        return None, "evidence"

    pack = build_evidence(ledger, root, days=days)
    agents = root / "AGENTS.md"
    current_block = ""
    if agents.is_file():
        text = agents.read_text(encoding="utf-8")
        if has_block(text):
            current_block = "\n".join(e.render() for e in parse_block(text))
    try:
        proposals = reflect(current_block, pack, backend)
    except ReflectorError as exc:
        print(f"Reflector failed ({exc}); using deterministic proposals.", file=sys.stderr)
        return None, "evidence"

    records = [
        ProposalRecord(
            op=p.op,
            entry=Entry(
                kind=p.kind,
                entry_id=p.entry_id,
                content=p.content.strip(),
                confidence=p.confidence,
            ),
            evidence=resolve_evidence(p),
            source=f"reflector:{backend}",
        )
        for p in proposals
    ]
    return records, backend


def _json_payload(insights: list[Any], records: list[ProposalRecord]) -> dict[str, Any]:
    return {
        "insights": [i.as_dict() for i in insights],
        "proposals": [
            {
                "op": r.op,
                "kind": r.entry.kind,
                "entry_id": r.entry.entry_id,
                "content": r.entry.content,
                "confidence": r.entry.confidence,
                "source": r.source,
                "candidates": r.candidates,
                "selected_index": r.selected_index,
                "evidence": r.evidence,
            }
            for r in records
        ],
    }


# ---------------------------------------------------------------------------
# Deterministic proposals (folded from proposals.py)
# ---------------------------------------------------------------------------

_SAVINGS_MAX_FRACTION = 0.5
_AVG_SEARCH_TOKENS = 1200
_AVG_READ_TOKENS = 1500
_TOOL_SCHEMA_TOKENS = 60


@dataclass
class _Suggestion:
    entry_id: str
    kind: str
    candidates: list[str]
    selected: int
    content: str
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8


def _stable_id(kind: str, key: str) -> str:
    return hashlib.sha1(f"{kind}:{key}".encode()).hexdigest()[:12]


def _weekly_spend(conn: sqlite3.Connection, days: int) -> float:
    row = conn.execute(
        "SELECT SUM(total_cost) AS cost FROM runs "
        "WHERE has_cost = 1 AND date(started_at) >= date('now', ?)",
        (f"-{days} days",),
    ).fetchone()
    cost = float(row["cost"] or 0) if row else 0.0
    return cost * (7.0 / max(1, days))


def _input_price(conn: sqlite3.Connection, days: int) -> float | None:
    row = conn.execute(
        "SELECT SUM(total_input_tokens) AS inp, SUM(total_cost) AS cost FROM runs "
        "WHERE has_cost = 1 AND total_input_tokens > 0 "
        "AND date(started_at) >= date('now', ?)",
        (f"-{days} days",),
    ).fetchone()
    if not row or not row["inp"] or not row["cost"]:
        return None
    inp = float(row["inp"])
    if inp <= 0:
        return None
    return (float(row["cost"]) * 0.6) / inp


def _cap_usd(raw_usd: float, weekly_spend: float) -> float:
    if weekly_spend <= 0:
        return round(raw_usd, 4)
    return round(min(raw_usd, weekly_spend * _SAVINGS_MAX_FRACTION), 4)


def _score_candidate(content: str, key_terms: list[str]) -> float:
    score = 0.0
    low = content.lower()
    for term in key_terms:
        if term and term.lower() in low:
            score += 1.0
    if "check " in low or "first" in low or "before" in low:
        score += 0.25
    return score


def _select(candidates: list[str], key_terms: list[str]) -> tuple[int, str]:
    scored = sorted(
        enumerate(candidates),
        key=lambda kv: (-_score_candidate(kv[1], key_terms), len(kv[1])),
    )
    idx, content = scored[0]
    return idx, content


def generate_proposals(
    conn: sqlite3.Connection, root: Path, *, days: int = 14
) -> list[ProposalRecord]:
    suggestions: list[_Suggestion] = []
    suggestions.extend(_identical_grep(conn, days))
    suggestions.extend(_repeated_reads(conn, days, root))
    suggestions.extend(_context_overflow(conn, days))
    suggestions.extend(_tool_errors(conn, days))
    suggestions.extend(_high_churn(conn, days, root))
    suggestions.extend(_unused_tool(conn, days))

    weekly_spend = _weekly_spend(conn, days)
    records: list[ProposalRecord] = []
    for s in suggestions:
        ev = dict(s.evidence)
        ev["candidates"] = s.candidates
        ev["selected_index"] = s.selected
        ev["weekly_spend_usd"] = round(weekly_spend, 4)
        records.append(
            ProposalRecord(
                op="add",
                entry=Entry(
                    kind=s.kind, entry_id=s.entry_id, content=s.content, confidence=s.confidence
                ),
                evidence=ev,
                source="evidence",
                candidates=s.candidates,
                selected_index=s.selected,
            )
        )
    return records


def _identical_grep(conn: sqlite3.Connection, days: int) -> list[_Suggestion]:
    row = conn.execute(
        """
        SELECT text_inline, COUNT(*) AS n, COUNT(DISTINCT run_id) AS sessions
        FROM events
        WHERE tool_norm_name = 'search' AND text_inline IS NOT NULL
          AND run_id IN (SELECT run_id FROM runs WHERE date(started_at) >= date('now', ?))
        GROUP BY text_hash HAVING n >= 3
        ORDER BY n DESC LIMIT 3
        """,
        (f"-{days} days",),
    ).fetchall()
    if not row:
        return []
    r = row[0]
    pattern = (r["text_inline"] or "")[:80]
    n = int(r["n"])
    sessions = int(r["sessions"])
    candidates = [
        "When searching for X, check project docs first before repeating grep across sessions.",
        f"When searching for `{pattern}`, check project docs first "
        "before repeating grep across sessions.",
        (
            f"Avoid repeating the search `{pattern}` — cache the result so later turns "
            f"don't re-grep ({n} repeats across {sessions} sessions)."
        ),
    ]
    idx, content = _select(candidates, [pattern])
    weekly_spend = _weekly_spend(conn, days)
    price = _input_price(conn, days)
    waste_tokens = (n - 1) * _AVG_SEARCH_TOKENS
    expected_usd = (
        _cap_usd(waste_tokens * (price or 0) * (7.0 / days), weekly_spend) if price else None
    )
    return [
        _Suggestion(
            entry_id=_stable_id("rule", pattern),
            kind="rule",
            candidates=candidates,
            selected=idx,
            content=content,
            evidence={
                "evidence_type": "identical_grep",
                "pattern": pattern,
                "searches": n,
                "sessions": sessions,
                "waste_tokens": waste_tokens,
                "expected_savings_tokens": waste_tokens,
                "expected_savings_usd": expected_usd,
            },
            confidence=min(0.5 + n * 0.05, 0.95),
        )
    ]


def _repeated_reads(conn: sqlite3.Connection, days: int, root: Path) -> list[_Suggestion]:
    rows = conn.execute(
        """
        SELECT path_rel, COUNT(*) AS n, COUNT(DISTINCT run_id) AS sessions
        FROM events
        WHERE tool_norm_name = 'read' AND path_rel IS NOT NULL
          AND run_id IN (SELECT run_id FROM runs WHERE date(started_at) >= date('now', ?))
        GROUP BY path_rel HAVING n >= 3
        ORDER BY n DESC LIMIT 3
        """,
        (f"-{days} days",),
    ).fetchall()
    weekly_spend = _weekly_spend(conn, days)
    price = _input_price(conn, days)
    out: list[_Suggestion] = []
    for r in rows:
        path = str(r["path_rel"])
        n = int(r["n"])
        sessions = int(r["sessions"])
        hint = _file_hint(root / path)
        candidates = [
            "The file `X` is frequently needed. Avoid re-reading it each session.",
            f"The file `{path}` is frequently needed ({hint}). Avoid re-reading it each session.",
            (
                f"`{path}` contains {hint}. Summarize it here and don't re-read "
                f"each session ({n} reads across {sessions} sessions)."
            ),
        ]
        idx, content = _select(candidates, [path, hint])
        waste_tokens = (n - sessions) * _AVG_READ_TOKENS
        expected_usd = (
            _cap_usd(waste_tokens * (price or 0) * (7.0 / days), weekly_spend) if price else None
        )
        out.append(
            _Suggestion(
                entry_id=_stable_id("file_guide", path),
                kind="file_guide",
                candidates=candidates,
                selected=idx,
                content=content,
                evidence={
                    "evidence_type": "repeated_file_reads",
                    "path": path,
                    "reads": n,
                    "sessions": sessions,
                    "waste_tokens": waste_tokens,
                    "expected_savings_tokens": waste_tokens,
                    "expected_savings_usd": expected_usd,
                },
                confidence=min(0.5 + n * 0.04, 0.92),
            )
        )
    return out


def _file_hint(path: Path) -> str:
    if not path.is_file():
        return "summarize key facts in AGENTS.md"
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[:30]:
            s = line.strip().lstrip("#").strip()
            if len(s) > 20:
                return s[:100]
    except OSError:
        pass
    return "summarize key facts in AGENTS.md"


def _context_overflow(conn: sqlite3.Connection, days: int) -> list[_Suggestion]:
    row = conn.execute(
        "SELECT COUNT(*) AS n, COUNT(DISTINCT run_id) AS sessions FROM runs "
        "WHERE peak_context_pct > 85 AND date(started_at) >= date('now', ?)",
        (f"-{days} days",),
    ).fetchone()
    if not row or int(row["n"] or 0) < 2:
        return []
    n = int(row["n"])
    sessions = int(row["sessions"])
    candidates = [
        "Split large tasks before context exceeds 70%. "
        "Use /compact or decompose when approaching limits.",
        "At >70% context, run /compact or split the task — don't wait for the 85% cliff.",
        (
            f"At >70% context, run /compact or split the task "
            f"({n} sessions hit >85% context in the last {days} days)."
        ),
    ]
    idx, content = _select(candidates, [str(n)])
    return [
        _Suggestion(
            entry_id=_stable_id("rule", "context"),
            kind="rule",
            candidates=candidates,
            selected=idx,
            content=content,
            evidence={
                "evidence_type": "context_overflow",
                "sessions_over_85pct": n,
                "sessions": sessions,
            },
            confidence=0.85,
        )
    ]


def _tool_errors(conn: sqlite3.Connection, days: int) -> list[_Suggestion]:
    rows = conn.execute(
        """
        SELECT tool_name, COUNT(*) AS n, COUNT(DISTINCT run_id) AS sessions
        FROM events
        WHERE tool_is_error = 1 AND tool_name IS NOT NULL
          AND run_id IN (SELECT run_id FROM runs WHERE date(started_at) >= date('now', ?))
        GROUP BY tool_name HAVING n >= 3
        ORDER BY n DESC LIMIT 3
        """,
        (f"-{days} days",),
    ).fetchall()
    out: list[_Suggestion] = []
    for r in rows:
        name = str(r["tool_name"])
        n = int(r["n"])
        sessions = int(r["sessions"])
        candidates = [
            "Tool `X` fails often in this repo — verify inputs before retrying.",
            (
                f"Tool `{name}` fails often in this repo — verify inputs before retrying "
                f"({n} failures across {sessions} sessions)."
            ),
            (
                f"`{name}` has failed {n}× across {sessions} sessions — check its inputs "
                "and add a guard before retrying."
            ),
        ]
        idx, content = _select(candidates, [name])
        out.append(
            _Suggestion(
                entry_id=_stable_id("known_issue", name),
                kind="known_issue",
                candidates=candidates,
                selected=idx,
                content=content,
                evidence={
                    "evidence_type": "tool_error_pattern",
                    "tool_name": name,
                    "failures": n,
                    "sessions": sessions,
                },
                confidence=0.8,
            )
        )
    return out


def _high_churn(conn: sqlite3.Connection, days: int, root: Path) -> list[_Suggestion]:
    row = conn.execute(
        """
        SELECT path_rel, COUNT(*) AS n, COUNT(DISTINCT run_id) AS sessions
        FROM events
        WHERE tool_norm_name = 'edit' AND path_rel IS NOT NULL
          AND run_id IN (SELECT run_id FROM runs WHERE date(started_at) >= date('now', ?))
        GROUP BY path_rel HAVING n >= 5
        ORDER BY n DESC LIMIT 1
        """,
        (f"-{days} days",),
    ).fetchone()
    if not row:
        return []
    path = str(row["path_rel"])
    n = int(row["n"])
    sessions = int(row["sessions"])
    candidates = [
        "Write a test for `X` before iterating on it.",
        f"`{path}` was edited {n} times — write a test before iterating.",
        (
            f"Define acceptance criteria (and a test) for `{path}` before iterating — "
            f"{n} edits across {sessions} sessions suggest churn."
        ),
    ]
    idx, content = _select(candidates, [path, str(n)])
    return [
        _Suggestion(
            entry_id=_stable_id("rule", f"churn:{path}"),
            kind="rule",
            candidates=candidates,
            selected=idx,
            content=content,
            evidence={
                "evidence_type": "high_churn",
                "path": path,
                "edits": n,
                "sessions": sessions,
            },
            confidence=0.75,
        )
    ]


def _unused_tool(conn: sqlite3.Connection, days: int) -> list[_Suggestion]:
    try:
        from cairn.profile.compute import _input_price_per_token, decompose_run
        from cairn.profile.detectors import detect_findings
    except Exception:
        return []
    runs = conn.execute(
        "SELECT run_id, model FROM runs WHERE date(started_at) >= date('now', ?)",
        (f"-{days} days",),
    ).fetchall()
    by_tool: dict[str, dict[str, Any]] = {}
    for r in runs:
        events = [
            dict(e)
            for e in conn.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY seq", (r["run_id"],)
            ).fetchall()
        ]
        if not events:
            continue
        model = str(r["model"]) if r["model"] else None
        try:
            result = decompose_run(events, model=model)
            price = _input_price_per_token(model)
            findings = detect_findings(events, result.regions, input_price_per_token=price)
        except Exception:
            continue
        for f in findings:
            if f.type != "UNUSED_TOOL_SCHEMA":
                continue
            tool = str(f.detail.get("tool") or "unknown")
            entry = by_tool.setdefault(tool, {"sessions": 0, "turns": 0, "wasted": 0, "fracs": []})
            entry["sessions"] += 1
            entry["turns"] += int(f.detail.get("total_turns", 0))
            entry["wasted"] += int(f.tokens or 0)
            entry["fracs"].append(float(f.detail.get("use_fraction", 0.0)))
    out: list[_Suggestion] = []
    weekly_spend = _weekly_spend(conn, days)
    price = _input_price(conn, days)
    for tool, v in by_tool.items():
        if not v["fracs"]:
            continue
        mean_use = sum(v["fracs"]) / len(v["fracs"])
        if mean_use > 0.1:
            continue
        turns_per_week = v["turns"] // 2
        waste_tokens = v["wasted"]
        expected_usd = (
            _cap_usd(waste_tokens * (price or 0) * (7.0 / days), weekly_spend) if price else None
        )
        candidates = [
            "Remove unused MCP tool `X` from the schema.",
            (
                f"Remove unused MCP tool `{tool}` — ~{_TOOL_SCHEMA_TOKENS} tokens/turn "
                f"× {turns_per_week} turns/wk."
            ),
            (
                f"Drop the `{tool}` tool definition — it's rarely called "
                f"({mean_use * 100:.0f}% use across {v['sessions']} sessions), "
                f"costing ~{_TOOL_SCHEMA_TOKENS} tokens/turn."
            ),
        ]
        idx, content = _select(candidates, [tool, str(turns_per_week)])
        out.append(
            _Suggestion(
                entry_id=_stable_id("rule", f"unused_tool:{tool}"),
                kind="rule",
                candidates=candidates,
                selected=idx,
                content=content,
                evidence={
                    "evidence_type": "unused_tool",
                    "tool": tool,
                    "sessions": v["sessions"],
                    "total_turns": v["turns"],
                    "waste_tokens": waste_tokens,
                    "tokens_per_turn": _TOOL_SCHEMA_TOKENS,
                    "expected_savings_tokens": waste_tokens,
                    "expected_savings_usd": expected_usd,
                },
                confidence=0.7,
            )
        )
    return out
