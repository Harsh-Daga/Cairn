"""Evidence packs — scrubbed input to the reflector and deterministic miner."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from server.improve.apply import MANAGED_START, has_block
from server.improve.context import build_context
from server.improve.proposals import generate_proposals
from server.ingest.constants import BYTES_PER_TOKEN

MAX_PACK_TOKENS = 8_000
_HEAD_LINES = 40
_ERROR_EXCERPT_CHARS = 500

_ENTRY_RE = re.compile(
    r"<!--\s*cairn:entry\s+(?P<kind>[^/]+)/(?P<eid>[^\s]+)"
    r"(?:\s+conf=(?P<conf>[0-9.]+))?\s*-->"
)


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

    def known_refs(self) -> set[str]:
        """Return evidence ref strings the reflector may cite."""
        refs: set[str] = set()
        for ins in self.insights:
            detector = str(ins.get("detector", ins.get("id", "")))
            if detector:
                refs.add(f"insight:{detector}")
                refs.add(detector)
            fingerprint = str(ins.get("fingerprint", ""))
            if fingerprint:
                refs.add(f"insight:{fingerprint}")
                refs.add(fingerprint)
        for item in self.reread_files:
            path = item.get("path")
            if path:
                refs.add(str(path))
        for cmd in self.failing_commands:
            name = cmd.get("name")
            if name:
                refs.add(str(name))
        for te in self.typed_evidence:
            entry_id = te.get("entry_id")
            if entry_id:
                refs.add(str(entry_id))
            etype = te.get("evidence_type")
            if etype:
                refs.add(f"evidence:{etype}")
        for entry in self.current_entries:
            entry_id = entry.get("entry_id")
            if entry_id:
                refs.add(str(entry_id))
        for category in self.waste:
            refs.add(f"waste:{category}")
        return refs


def build_evidence_pack(
    conn: sqlite3.Connection,
    root: Path,
    *,
    workspace_id: str,
    days: int = 14,
) -> EvidencePack:
    """Construct a scrubbed evidence pack for the trailing ``days`` window."""
    ctx = build_context(conn, workspace_id=workspace_id, days=days)
    waste: dict[str, Any] = {}
    for cat, stats in (
        ("identical_call", ctx.get("identical_call_tokens", 0)),
        ("oversize_result", ctx.get("oversize_result_tokens", 0)),
        ("retry_loop", ctx.get("retry_loop_events", 0)),
    ):
        if isinstance(stats, int) and stats > 0:
            waste[cat] = {"tokens": stats, "events": stats}

    insights = _insights_from_context(ctx)
    typed = _typed_evidence(conn, limit=10)
    pack = EvidencePack(
        days=days,
        insights=insights,
        waste=waste,
        reread_files=_reread_files(conn, workspace_id, days, root),
        failing_commands=_failing_commands(conn, workspace_id, days),
        loops=_retry_loops(ctx),
        current_entries=_current_entries(root),
        typed_evidence=typed,
    )
    _enforce_budget(pack)
    return pack


def _insights_from_context(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Summarize high-signal context fields as insight-shaped dicts."""
    out: list[dict[str, Any]] = []
    if int(ctx.get("identical_call_events", 0)) > 0:
        out.append(
            {
                "detector": "identical-tool-calls",
                "fingerprint": "identical-tool-calls",
                "events": int(ctx["identical_call_events"]),
                "waste_tokens": int(ctx.get("identical_call_tokens", 0)),
            }
        )
    if int(ctx.get("retry_loop_events", 0)) > 0:
        out.append(
            {
                "detector": "retry-loops-detected",
                "fingerprint": "retry-loops-detected",
                "events": int(ctx["retry_loop_events"]),
            }
        )
    for session in ctx.get("high_context_sessions", []) or []:
        out.append(
            {
                "detector": "context-window-pressure",
                "fingerprint": "context-window-pressure",
                "run_id": session.get("run_id"),
                "peak_context_pct": session.get("peak_context_pct"),
            }
        )
    return out


def _typed_evidence(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, Any]]:
    records = generate_proposals(conn, limit=limit)
    return [
        {
            "evidence_type": "insight_proposal",
            "kind": r.kind,
            "entry_id": r.block_key,
            "proposed_instruction": r.content,
            "evidence_id": r.evidence_id,
            "rationale": r.rationale,
        }
        for r in records
    ]


def _reread_files(
    conn: sqlite3.Connection, workspace_id: str, days: int, root: Path
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.path_rel, COUNT(*) AS n
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE s.name = 'read' AND s.path_rel IS NOT NULL
          AND t.workspace_id = ?
          AND date(t.started_at) >= date('now', ?)
        GROUP BY s.path_rel HAVING n >= 3
        ORDER BY n DESC LIMIT 10
        """,
        (workspace_id, f"-{days} days"),
    ).fetchall()
    return [
        {
            "path": str(r["path_rel"]),
            "reads": int(r["n"]),
            "head": _file_head(root / str(r["path_rel"])),
        }
        for r in rows
    ]


def _failing_commands(
    conn: sqlite3.Connection, workspace_id: str, days: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT s.name, COUNT(*) AS failures, MAX(s.trace_id) AS trace_id, MAX(s.seq) AS seq
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE s.status = 'error' AND s.name IS NOT NULL
          AND t.workspace_id = ?
          AND date(t.started_at) >= date('now', ?)
        GROUP BY s.name
        HAVING failures >= 1
        ORDER BY failures DESC
        LIMIT 10
        """,
        (workspace_id, f"-{days} days"),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        excerpt = _event_excerpt(conn, str(r["trace_id"]), int(r["seq"]))
        out.append({"name": r["name"], "failures": int(r["failures"]), "last_error": excerpt})
    return out


def _event_excerpt(conn: sqlite3.Connection, trace_id: str, seq: int) -> str:
    row = conn.execute(
        "SELECT text_inline FROM spans WHERE trace_id = ? AND seq = ?", (trace_id, seq)
    ).fetchone()
    if not row:
        return ""
    text = str(row["text_inline"] or "")
    return text[:_ERROR_EXCERPT_CHARS]


def _retry_loops(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    count = int(ctx.get("retry_loop_events", 0))
    if count <= 0:
        return []
    return [{"kind": "retry_loop", "description": f"{count} retry loops detected", "seqs": []}]


def _current_entries(root: Path) -> list[dict[str, Any]]:
    agents = root / "AGENTS.md"
    if not agents.is_file():
        return []
    text = agents.read_text(encoding="utf-8")
    if not has_block(text):
        return []
    entries: list[dict[str, Any]] = []
    for match in _ENTRY_RE.finditer(text):
        conf_raw = match.group("conf")
        confidence = float(conf_raw) if conf_raw else 0.8
        entries.append(
            {
                "kind": match.group("kind"),
                "entry_id": match.group("eid"),
                "content": "",
                "confidence": confidence,
            }
        )
    if MANAGED_START not in text:
        return entries
    return entries


def _file_head(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[:_HEAD_LINES])


def _enforce_budget(pack: EvidencePack) -> None:
    """Truncate the largest excerpts first until the pack fits MAX_PACK_TOKENS."""
    if pack.approx_tokens() <= MAX_PACK_TOKENS:
        return
    for item in pack.reread_files:
        item["head"] = ""
    if pack.approx_tokens() <= MAX_PACK_TOKENS:
        return
    for cmd in pack.failing_commands:
        cmd["last_error"] = ""
    if pack.approx_tokens() <= MAX_PACK_TOKENS:
        return
    pack.loops = pack.loops[:3]
    pack.reread_files = pack.reread_files[:5]
    pack.insights = pack.insights[:8]
