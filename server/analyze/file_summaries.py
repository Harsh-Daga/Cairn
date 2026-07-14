"""Bounded deterministic summaries for frequently re-read workspace files."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from server.analyze.views import IncrementalView, trace_input_hash

MAX_SUMMARY_TOKENS = 120
MAX_FILE_BYTES = 256_000
HOT_READ_COUNT = 2


class FileSummaryView(IncrementalView):
    """Cache file identity and a compact summary once a file becomes hot."""

    view_name = "file_summaries"
    VERSION = 1

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id

    def keys_for(self, trace_id: str) -> list[str]:
        return [trace_id]

    def input_hash_for(self, conn: sqlite3.Connection, key: str) -> str:
        return trace_input_hash(conn, key)

    def compute(self, conn: sqlite3.Connection, key: str) -> None:
        workspace = conn.execute(
            "SELECT root_path FROM workspaces WHERE workspace_id = ?",
            (self.workspace_id,),
        ).fetchone()
        if workspace is None:
            return
        root = Path(str(workspace["root_path"])).resolve()
        paths = conn.execute(
            """
            SELECT DISTINCT path_rel FROM spans
            WHERE trace_id = ? AND path_rel IS NOT NULL
              AND (name IN ('read','search','grep','glob') OR name LIKE '%read%')
            """,
            (key,),
        ).fetchall()
        for path_row in paths:
            path_rel = str(path_row["path_rel"])
            aggregate = conn.execute(
                """
                SELECT COUNT(*) AS reads, MAX(s.started_at) AS last_read_at
                FROM spans s JOIN traces t ON t.trace_id = s.trace_id
                WHERE t.workspace_id = ? AND s.path_rel = ?
                  AND (s.name IN ('read','search','grep','glob') OR s.name LIKE '%read%')
                """,
                (self.workspace_id, path_rel),
            ).fetchone()
            reads = int(aggregate["reads"] or 0) if aggregate else 0
            if reads < HOT_READ_COUNT:
                continue
            target = _safe_target(root, path_rel)
            content_hash: str | None = None
            mtime_ns: int | None = None
            summary: str | None = None
            summary_tokens = 0
            if target is not None and target.is_file():
                raw = target.read_bytes()[:MAX_FILE_BYTES]
                content_hash = hash_file(target)
                mtime_ns = target.stat().st_mtime_ns
                summary = summarize_file(raw.decode("utf-8", errors="replace"))
                summary_tokens = len(summary.split()) if summary else 0
            conn.execute(
                """
                INSERT INTO file_read_cache (
                  workspace_id, path_rel, content_hash, file_mtime_ns, summary,
                  summary_tokens, read_count, last_read_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id, path_rel) DO UPDATE SET
                  content_hash = excluded.content_hash,
                  file_mtime_ns = excluded.file_mtime_ns,
                  summary = excluded.summary,
                  summary_tokens = excluded.summary_tokens,
                  read_count = excluded.read_count,
                  last_read_at = excluded.last_read_at,
                  updated_at = excluded.updated_at
                """,
                (
                    self.workspace_id,
                    path_rel,
                    content_hash,
                    mtime_ns,
                    summary,
                    summary_tokens,
                    reads,
                    aggregate["last_read_at"] if aggregate else None,
                    datetime.now(UTC).isoformat(),
                ),
            )


def summarize_file(text: str) -> str | None:
    """Return at most 120 whitespace tokens of structural, non-generated context."""
    candidates: list[str] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip().split())
        if not line:
            continue
        if (
            line.startswith(("#", "class ", "def ", "async def ", "export ", "interface "))
            or len(candidates) < 3
        ):
            candidates.append(line)
        if len(candidates) >= 20:
            break
    words = " ".join(candidates).split()
    if not words:
        return None
    if len(words) > MAX_SUMMARY_TOKENS:
        return " ".join([*words[: MAX_SUMMARY_TOKENS - 1], "…"])
    return " ".join(words)


def _safe_target(root: Path, path_rel: str) -> Path | None:
    target = (root / path_rel).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None
    return target


def hash_file(path: Path) -> str:
    """Hash the complete file without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
