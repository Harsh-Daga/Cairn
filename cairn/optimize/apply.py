"""Apply proposals to instruction files safely, recording baselines for later impact."""

from __future__ import annotations

import difflib
import json
import re
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cairn.ledger.ledger import Ledger
from cairn.metrics.constants import MANAGED_BLOCK_MAX_CHARS, MANAGED_BLOCK_MAX_LINES
from cairn.optimize.impact import classify, measure_metric
from cairn.optimize.targets import TargetPlan, detect_targets

# --- managed instruction block (folded from block.py) -----------------------

MANAGED_START = "<!-- cairn:managed start (do not edit inside; `cairn optimize` maintains this) -->"
MANAGED_END = "<!-- cairn:managed end -->"

_BLOCK_HEADING = "## Agent guide (auto-maintained by cairn from session evidence)"

_KIND_SECTIONS: tuple[tuple[str, str], ...] = (
    ("command_fix", "### Commands that work"),
    ("known_issue", "### Known issues"),
    ("file_guide", "### File guide"),
    ("repo_map", "### Repo map"),
    ("rule", "### Rules"),
)
_KIND_ORDER = {kind: i for i, (kind, _) in enumerate(_KIND_SECTIONS)}

_KINDS = "|".join(kind for kind, _ in _KIND_SECTIONS)
_ENTRY_RE = re.compile(
    r"<!--\s*cairn:entry\s+(?P<kind>" + _KINDS + r")/(?P<eid>[^\s/]+)"
    r"(?:\s+conf=(?P<conf>[0-9.]+))?\s*-->"
)


class BlockError(Exception):
    """Raised when managed-block markers are missing, unbalanced, or nested."""


@dataclass
class Entry:
    kind: str
    entry_id: str
    content: str
    confidence: float = 0.8

    def render(self) -> str:
        conf = f" conf={self.confidence:g}" if self.confidence is not None else ""
        marker = f"<!-- cairn:entry {self.kind}/{self.entry_id}{conf} -->"
        return f"- {self.content}  {marker}"


def has_block(text: str) -> bool:
    return MANAGED_START in text and MANAGED_END in text


def _locate_block(text: str) -> tuple[int, int]:
    starts = [m.start() for m in re.finditer(re.escape(MANAGED_START), text)]
    ends = [m.start() for m in re.finditer(re.escape(MANAGED_END), text)]
    if not starts and not ends:
        raise BlockError("no managed block found")
    if len(starts) != 1 or len(ends) != 1:
        raise BlockError("managed-block markers are unbalanced or nested; refusing to edit")
    start, end = starts[0], ends[0]
    if end < start:
        raise BlockError("managed-block end marker precedes start marker; refusing to edit")
    return start, end + len(MANAGED_END)


def parse_block(text: str) -> list[Entry]:
    start, end = _locate_block(text)
    inner = text[start:end]
    entries: list[Entry] = []
    for line in inner.splitlines():
        m = _ENTRY_RE.search(line)
        if not m:
            continue
        content = line[: m.start()].strip()
        if content.startswith("- "):
            content = content[2:].strip()
        conf = float(m.group("conf")) if m.group("conf") else 0.8
        entries.append(
            Entry(kind=m.group("kind"), entry_id=m.group("eid"), content=content, confidence=conf)
        )
    return entries


def serialize_block(entries: list[Entry]) -> str:
    ordered = sorted(entries, key=lambda e: (_KIND_ORDER.get(e.kind, 99), e.entry_id))
    lines: list[str] = [MANAGED_START, _BLOCK_HEADING]
    for kind, heading in _KIND_SECTIONS:
        group = [e for e in ordered if e.kind == kind]
        if not group:
            continue
        lines.append(heading)
        lines.extend(e.render() for e in group)
    lines.append(MANAGED_END)
    return "\n".join(lines)


def replace_block(text: str, entries: list[Entry]) -> str:
    block = serialize_block(entries)
    if has_block(text):
        start, end = _locate_block(text)
        return text[:start] + block + text[end:]
    sep = "" if text.endswith("\n") or text == "" else "\n"
    prefix = text + sep
    if prefix and not prefix.endswith("\n\n"):
        prefix += "\n"
    return f"{prefix}{block}\n"


def consolidate(entries: list[Entry]) -> list[Entry]:
    """Merge duplicates by (kind, entry_id) and enforce managed-block caps."""
    merged: dict[tuple[str, str], Entry] = {}
    for e in entries:
        key = (e.kind, e.entry_id)
        existing = merged.get(key)
        if existing is None or e.confidence > existing.confidence:
            merged[key] = e
    kept = list(merged.values())
    kept.sort(key=lambda e: e.confidence, reverse=True)
    while kept and not _within_caps(kept):
        kept.pop()
    return kept


def _within_caps(entries: list[Entry]) -> bool:
    block = serialize_block(entries)
    return block.count("\n") <= MANAGED_BLOCK_MAX_LINES and len(block) <= MANAGED_BLOCK_MAX_CHARS


_BRIDGE_POINTER = "See AGENTS.md for project rules (maintained by cairn)."
_CLAUDE_IMPORT = "@AGENTS.md"


@dataclass
class ProposalRecord:
    op: str  # add | update | remove
    entry: Entry
    evidence: dict[str, Any] = field(default_factory=dict)
    source: str = "miner"
    candidates: list[str] = field(default_factory=list)
    selected_index: int = 0


@dataclass
class ApplyResult:
    applied: int
    diff: str
    refused: str | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# --- preview / diff -------------------------------------------------------------------


def _merge_entries(existing: list[Entry], records: list[ProposalRecord]) -> list[Entry]:
    by_key: dict[tuple[str, str], Entry] = {(e.kind, e.entry_id): e for e in existing}
    for r in records:
        key = (r.entry.kind, r.entry.entry_id)
        if r.op == "remove":
            by_key.pop(key, None)
        else:  # add | update
            by_key[key] = r.entry
    return consolidate(list(by_key.values()))


def _agents_text(root: Path) -> str:
    p = root / "AGENTS.md"
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _existing_entries(text: str) -> list[Entry]:
    if not has_block(text):
        return []
    try:
        return parse_block(text)
    except Exception:
        return []


def preview_diff(root: Path, records: list[ProposalRecord]) -> str:
    """Unified diff of AGENTS.md after applying ``records`` (no write)."""
    current = _agents_text(root)
    merged = _merge_entries(_existing_entries(current), records)
    updated = replace_block(current, merged)
    return _unified(current, updated, "AGENTS.md")


def _unified(before: str, after: str, label: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
    )
    return "".join(diff)


# --- git safety -----------------------------------------------------------------------


def _git(root: Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return 1, ""
    return proc.returncode, proc.stdout


def _strip_block(text: str) -> str:
    if not has_block(text):
        return text
    start = text.index(MANAGED_START)
    end = text.index(MANAGED_END) + len(MANAGED_END)
    return text[:start] + text[end:]


def _dirty_outside_block(root: Path, rel: str) -> bool:
    """True if ``rel`` has uncommitted changes outside its managed block."""
    code, _ = _git(root, "rev-parse", "--is-inside-work-tree")
    if code != 0:
        return False  # not a git repo; cannot check, allow
    code, _ = _git(root, "ls-files", "--error-unmatch", rel)
    if code != 0:
        return False  # untracked/new file; nothing committed to clobber
    code, head = _git(root, "show", f"HEAD:{rel}")
    if code != 0:
        return False
    work = (root / rel).read_text(encoding="utf-8") if (root / rel).is_file() else ""
    # Equal once the managed block is removed from both -> only the block changed.
    return _strip_block(head) != _strip_block(work)


# --- apply ----------------------------------------------------------------------------


def apply_proposals(
    root: Path,
    records: list[ProposalRecord],
    *,
    force: bool = False,
    observed_sources: set[str] | None = None,
    plan: TargetPlan | None = None,
) -> ApplyResult:
    """Write proposals into AGENTS.md + bridges; record baselines in the ledger."""
    if not records:
        return ApplyResult(applied=0, diff="")

    if not force and _dirty_outside_block(root, "AGENTS.md"):
        return ApplyResult(
            applied=0,
            diff="",
            refused="AGENTS.md has uncommitted changes outside the managed block; "
            "commit them or re-run with --force.",
        )

    current = _agents_text(root)
    diff = preview_diff(root, records)
    merged = _merge_entries(_existing_entries(current), records)
    _backup(root, "AGENTS.md")
    (root / "AGENTS.md").write_text(replace_block(current, merged), encoding="utf-8")

    plan = plan or detect_targets(root, observed_sources=observed_sources)
    _write_bridges(plan)

    _record_optimizations(root, records)
    return ApplyResult(applied=len([r for r in records if r.op != "remove"]), diff=diff)


def _backup(root: Path, rel: str) -> None:
    """Copy the current target to ``.cairn/backups/`` before overwriting it."""
    src = root / rel
    if not src.is_file():
        return
    try:
        import shutil

        backup_dir = root / ".cairn" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        dest = backup_dir / f"{rel.replace('/', '__')}.{stamp}.bak"
        shutil.copy2(src, dest)
    except OSError:
        pass


def _write_bridges(plan: TargetPlan) -> None:
    for bridge in plan.bridges:
        path = plan.root / bridge.path
        if bridge.path == "CLAUDE.md":
            _write_managed_region(path, _CLAUDE_IMPORT)
        elif bridge.path == ".cursorrules":
            _write_managed_region(path, _BRIDGE_POINTER)
        else:
            _write_managed_region(path, _BRIDGE_POINTER)


def _write_managed_region(path: Path, body: str) -> None:
    region = f"{MANAGED_START}\n{body}\n{MANAGED_END}\n"
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        if has_block(text):
            start = text.index(MANAGED_START)
            end = text.index(MANAGED_END) + len(MANAGED_END)
            new = text[:start] + region.rstrip("\n") + text[end:]
        else:
            sep = "" if text.endswith("\n") or text == "" else "\n"
            new = text + sep + region
        if new != text:
            path.write_text(new, encoding="utf-8")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(region, encoding="utf-8")


def _record_optimizations(root: Path, records: list[ProposalRecord]) -> None:
    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        conn = ledger.connection
        now = _now_iso()
        today = str(conn.execute("SELECT date('now')").fetchone()[0])
        start = (datetime.now(UTC) - timedelta(days=14)).date().isoformat()
        baseline_sessions = _session_count(conn, start, today)
        fp_baseline = _fingerprint_distance_window(conn, start, today)
        for r in records:
            if r.op == "remove":
                conn.execute(
                    "UPDATE optimizations SET status = 'reverted' WHERE block_key = ? AND kind = ?",
                    (r.entry.entry_id, r.entry.kind),
                )
                continue
            baseline = measure_metric(
                conn, r.entry.kind, r.evidence, start_day=start, end_day=today
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO optimizations (
                  opt_id, created_at, target_file, block_key, kind, content,
                  evidence_json, status, applied_at, baseline_metric,
                  baseline_sessions, fingerprint_distance_baseline
                ) VALUES (?, ?, 'AGENTS.md', ?, ?, ?, ?, 'applied', ?, ?, ?, ?)
                """,
                (
                    f"opt-{uuid.uuid4().hex[:12]}",
                    now,
                    r.entry.entry_id,
                    r.entry.kind,
                    r.entry.content,
                    json.dumps(r.evidence),
                    now,
                    baseline,
                    baseline_sessions,
                    fp_baseline,
                ),
            )
        conn.commit()
    finally:
        ledger.close()


def _session_count(conn: sqlite3.Connection, start: str, end: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM runs "
        "WHERE date(started_at) >= date(?) AND date(started_at) <= date(?)",
        (start, end),
    ).fetchone()
    return int(row["n"] if row else 0)


def _fingerprint_distance_window(conn: sqlite3.Connection, start: str, end: str) -> float | None:
    """Mean Mahalanobis distance of fingerprints in the window vs prior baseline.

    Best-effort: requires >=4 prior fingerprint vectors for the primary
    project/model. Returns None (no fabrication) when insufficient.
    """
    try:
        from cairn.metrics.fingerprint import _baseline_vectors_for, detect_drift
    except Exception:
        return None
    row = conn.execute(
        """
        SELECT f.project, f.model, f.run_id, f.week, f.vector_json
        FROM fingerprints f
        WHERE date(f.ts) >= date(?) AND date(f.ts) <= date(?)
        ORDER BY f.ts DESC LIMIT 50
        """,
        (start, end),
    ).fetchall()
    if not row:
        return None
    project = str(row[0]["project"] or "")
    model = str(row[0]["model"] or "")
    distances: list[float] = []
    for r in row:
        try:
            vec = json.loads(r["vector_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        baseline = _baseline_vectors_for(conn, project, model, before_week=r["week"])
        if len(baseline) < 4:
            continue
        res = detect_drift(vec, baseline)
        if res.distance is not None:
            distances.append(res.distance)
    if not distances:
        return None
    return round(sum(distances) / len(distances), 4)


# --- revert / prune -------------------------------------------------------------------


def revert_entries(root: Path, spec: str) -> int:
    """Remove entries from AGENTS.md (``all`` or a specific entry_id)."""
    current = _agents_text(root)
    entries = _existing_entries(current)
    if spec == "all":
        kept: list[Entry] = []
        removed = entries
    else:
        kept = [e for e in entries if e.entry_id != spec]
        removed = [e for e in entries if e.entry_id == spec]
    if not removed:
        print(f"No entry matching {spec!r}.")
        return 0
    (root / "AGENTS.md").write_text(replace_block(current, kept), encoding="utf-8")
    _set_status(root, [e.entry_id for e in removed], "reverted")
    print(f"Reverted {len(removed)} entr{'y' if len(removed) == 1 else 'ies'}.")
    return 0


def prune_entries(root: Path) -> int:
    """Remove applied entries whose verdict is neutral or worsened."""
    from cairn.optimize.impact import compute_outcomes

    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        compute_outcomes(ledger)
        rows = ledger.connection.execute(
            "SELECT block_key, outcome_metric FROM optimizations WHERE status = 'applied'"
        ).fetchall()
        prune_ids = [
            str(r["block_key"])
            for r in rows
            if r["outcome_metric"] is not None
            and classify(1.0, float(r["outcome_metric"])) == "worsened"
        ]
    finally:
        ledger.close()

    if not prune_ids:
        print("Nothing to prune — no neutral or worsened entries.")
        return 0
    current = _agents_text(root)
    entries = _existing_entries(current)
    kept = [e for e in entries if e.entry_id not in set(prune_ids)]
    (root / "AGENTS.md").write_text(replace_block(current, kept), encoding="utf-8")
    _set_status(root, prune_ids, "pruned")
    print(f"Pruned {len(prune_ids)} entr{'y' if len(prune_ids) == 1 else 'ies'}.")
    return 0


def _set_status(root: Path, entry_ids: list[str], status: str) -> None:
    if not entry_ids:
        return
    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        conn = ledger.connection
        for eid in entry_ids:
            conn.execute(
                "UPDATE optimizations SET status = ? WHERE block_key = ?",
                (status, eid),
            )
        conn.commit()
    finally:
        ledger.close()
