"""Evidence packs — the scrubbed input to the reflector and the deterministic miner."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cairn.insights.engine import evaluate
from cairn.ledger.ledger import Ledger
from cairn.metrics.constants import BYTES_PER_TOKEN
from cairn.optimize.apply import parse_block
from cairn.render.scrub import scrub_text

MAX_PACK_TOKENS = 8_000
_HEAD_LINES = 40
_ERROR_EXCERPT_CHARS = 500
_TRACE_EVENTS = 3


@dataclass
class EvidencePack:
    days: int
    insights: list[dict[str, Any]] = field(default_factory=list)
    waste: dict[str, Any] = field(default_factory=dict)
    reread_files: list[dict[str, Any]] = field(default_factory=list)
    failing_commands: list[dict[str, Any]] = field(default_factory=list)
    loops: list[dict[str, Any]] = field(default_factory=list)
    current_entries: list[dict[str, Any]] = field(default_factory=list)
    typed_evidence: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "days": self.days,
            "insights": self.insights,
            "waste": self.waste,
            "reread_files": self.reread_files,
            "failing_commands": self.failing_commands,
            "loops": self.loops,
            "current_entries": self.current_entries,
            "typed_evidence": self.typed_evidence,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), separators=(",", ":"), ensure_ascii=False)

    def approx_tokens(self) -> int:
        return len(self.to_json()) // BYTES_PER_TOKEN


def _reread_files(conn: sqlite3.Connection, days: int, root: Path) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT path_rel, COUNT(*) AS n
        FROM events
        WHERE tool_norm_name = 'read' AND path_rel IS NOT NULL
          AND run_id IN (
            SELECT run_id FROM runs WHERE date(started_at) >= date('now', ?)
          )
        GROUP BY path_rel HAVING n >= 3
        ORDER BY n DESC LIMIT 10
        """,
        (f"-{days} days",),
    ).fetchall()
    return [
        {
            "path": str(r["path_rel"]),
            "reads": int(r["n"]),
            "head": _file_head(root / str(r["path_rel"])),
        }
        for r in rows
    ]


def build_evidence(ledger: Ledger, root: Path, *, days: int = 14) -> EvidencePack:
    """Construct a scrubbed evidence pack for the trailing ``days`` window."""
    insights = [i.as_dict() for i in evaluate(ledger, days=days)]
    typed = _typed_evidence(ledger.connection, root, days=days)
    pack = EvidencePack(
        days=days,
        insights=insights,
        waste=_waste_aggregates(ledger, days=days),
        reread_files=_reread_files(ledger.connection, days, root),
        failing_commands=_failing_commands(ledger, days=days),
        loops=_retry_loops(ledger, days=days),
        current_entries=_current_entries(root),
        typed_evidence=typed,
    )
    _enforce_budget(pack)
    return pack


def _typed_evidence(conn: sqlite3.Connection, root: Path, *, days: int) -> list[dict[str, Any]]:
    """The 6 evidence types (§2.7E) with token economics + proposed instruction.

    Reuses the deterministic proposal miner so the reflector and the proposals
    see the same evidence. Free-text is scrubbed because a pack may leave the
    machine via an LLM backend.
    """
    from cairn.optimize.engine import generate_proposals

    try:
        records = generate_proposals(conn, root, days=days)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for r in records:
        ev = dict(r.evidence)
        etype = str(ev.get("evidence_type", "unknown"))
        # Scrub any free-text fields that could leak local content.
        for key in ("pattern", "path", "tool_name"):
            if key in ev and isinstance(ev[key], str):
                ev[key] = scrub_text(ev[key])
        out.append(
            {
                "evidence_type": etype,
                "kind": r.entry.kind,
                "entry_id": r.entry.entry_id,
                "proposed_instruction": scrub_text(r.entry.content),
                "candidates": [scrub_text(c) for c in r.candidates],
                "selected_index": r.selected_index,
                "token_economics": {
                    "waste_tokens": ev.get("waste_tokens", ev.get("waste_tokens", 0)),
                    "expected_savings_tokens": ev.get("expected_savings_tokens"),
                    "expected_savings_usd": ev.get("expected_savings_usd"),
                },
                "confidence": r.entry.confidence,
                "detail": {
                    k: v
                    for k, v in ev.items()
                    if k not in ("candidates", "selected_index", "weekly_spend_usd")
                },
            }
        )
    return out


def _waste_aggregates(ledger: Ledger, *, days: int) -> dict[str, Any]:
    rows = ledger.connection.execute(
        """
        SELECT waste_category, SUM(waste_tokens) AS tokens, COUNT(*) AS events
        FROM events e
        JOIN runs r ON r.run_id = e.run_id
        WHERE e.waste_category IS NOT NULL AND date(r.started_at) >= date('now', ?)
        GROUP BY waste_category
        """,
        (f"-{days} days",),
    ).fetchall()
    return {
        str(r["waste_category"]): {"tokens": int(r["tokens"] or 0), "events": int(r["events"])}
        for r in rows
    }


def _file_head(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    head = "\n".join(text.splitlines()[:_HEAD_LINES])
    return scrub_text(head)


def _failing_commands(ledger: Ledger, *, days: int) -> list[dict[str, Any]]:
    rows = ledger.connection.execute(
        """
        SELECT tool_name AS name, COUNT(*) AS failures,
               MAX(run_id) AS run_id, MAX(seq) AS seq
        FROM events
        WHERE tool_is_error = 1 AND tool_name IS NOT NULL
          AND run_id IN (
            SELECT run_id FROM runs WHERE date(started_at) >= date('now', ?)
          )
        GROUP BY tool_name
        HAVING failures >= 1
        ORDER BY failures DESC
        LIMIT 10
        """,
        (f"-{days} days",),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        excerpt = _event_excerpt(ledger, str(r["run_id"]), int(r["seq"]))
        out.append({"name": r["name"], "failures": int(r["failures"]), "last_error": excerpt})
    return out


def _event_excerpt(ledger: Ledger, run_id: str, seq: int) -> str:
    row = ledger.connection.execute(
        "SELECT text_inline FROM events WHERE run_id = ? AND seq = ?", (run_id, seq)
    ).fetchone()
    if not row:
        return ""
    return scrub_text(str(row["text_inline"] or ""))[:_ERROR_EXCERPT_CHARS]


def _retry_loops(ledger: Ledger, *, days: int) -> list[dict[str, Any]]:
    rows = ledger.connection.execute(
        """
        SELECT waste_category, COUNT(*) AS n
        FROM events e
        JOIN runs r ON r.run_id = e.run_id
        WHERE e.waste_category = 'retry_loop' AND date(r.started_at) >= date('now', ?)
        GROUP BY waste_category
        """,
        (f"-{days} days",),
    ).fetchall()
    return [
        {"kind": "retry_loop", "description": f"{int(r['n'])} retry loops detected", "seqs": []}
        for r in rows
    ]


def _current_entries(root: Path) -> list[dict[str, Any]]:
    agents = root / "AGENTS.md"
    if not agents.is_file():
        return []
    try:
        entries = parse_block(agents.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [
        {"kind": e.kind, "entry_id": e.entry_id, "content": e.content, "confidence": e.confidence}
        for e in entries
    ]


def _enforce_budget(pack: EvidencePack) -> None:
    """Truncate the largest excerpts first until the pack fits MAX_PACK_TOKENS."""
    if pack.approx_tokens() <= MAX_PACK_TOKENS:
        return
    # 1. Drop file heads (the biggest free-text fields).
    for f in pack.reread_files:
        f["head"] = ""
    if pack.approx_tokens() <= MAX_PACK_TOKENS:
        return
    # 2. Drop error excerpts.
    for c in pack.failing_commands:
        c["last_error"] = ""
    if pack.approx_tokens() <= MAX_PACK_TOKENS:
        return
    # 3. Trim list lengths as a last resort.
    pack.loops = pack.loops[:3]
    pack.reread_files = pack.reread_files[:5]
    pack.insights = pack.insights[:8]
