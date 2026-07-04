"""Migration runner — applies append-only SQL migrations (Phase 1)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

MIGRATIONS_DIR = "migrations"
FTS_AVAILABLE = True

_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS _migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);
"""

_FTS_DDL = (
    "CREATE VIRTUAL TABLE spans_fts USING fts5("
    "trace_id UNINDEXED, span_id UNINDEXED, text_inline"
    ");"
)


def _migrations_path() -> Path:
    return Path(__file__).resolve().parent / MIGRATIONS_DIR


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_MIGRATIONS_DDL)


def _applied_versions(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT version FROM _migrations").fetchall()
    return {str(row[0]) for row in rows}


def _split_fts(sql: str) -> tuple[str, str | None]:
    """Separate best-effort FTS DDL from the main migration script."""
    lines: list[str] = []
    fts_sql: str | None = None
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("CREATE VIRTUAL TABLE") and "spans_fts" in stripped:
            fts_sql = stripped.rstrip(";") + ";"
            continue
        if stripped.startswith("-- FTS"):
            continue
        lines.append(line)
    return "\n".join(lines).strip(), fts_sql


def _try_create_fts(conn: sqlite3.Connection, fts_sql: str | None = None) -> bool:
    global FTS_AVAILABLE
    ddl = (fts_sql or _FTS_DDL).rstrip(";") + ";"
    try:
        conn.executescript(ddl)
        FTS_AVAILABLE = True
        return True
    except sqlite3.OperationalError:
        FTS_AVAILABLE = False
        return False


def _apply_migration(conn: sqlite3.Connection, sql: str) -> None:
    main_sql, fts_sql = _split_fts(sql)
    if main_sql:
        conn.executescript(main_sql)
    _try_create_fts(conn, fts_sql)


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply pending SQL migrations in filename order; skip already applied."""
    _ensure_migrations_table(conn)
    applied = _applied_versions(conn)
    newly_applied: list[str] = []

    for path in sorted(_migrations_path().glob("*.sql")):
        version = path.stem
        if version in applied:
            continue
        _apply_migration(conn, path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO _migrations (version, applied_at) VALUES (?, ?)",
            (version, datetime.now(UTC).isoformat()),
        )
        newly_applied.append(version)

    conn.commit()
    return newly_applied
