"""Migration runner — applies append-only SQL migrations (Phase 1)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from server.util.private_files import ensure_private_dir, ensure_private_file

MIGRATIONS_DIR = "migrations"
FTS_AVAILABLE = True

_FTS_DDL = (
    "CREATE VIRTUAL TABLE spans_fts USING fts5(trace_id UNINDEXED, span_id UNINDEXED, text_inline);"
)


def _migrations_path() -> Path:
    return Path(__file__).resolve().parent / MIGRATIONS_DIR


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS _migrations (
             version TEXT PRIMARY KEY,
             applied_at TEXT NOT NULL
           )"""
    )
    conn.commit()


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
        conn.execute(ddl)
        FTS_AVAILABLE = True
        return True
    except sqlite3.OperationalError:
        FTS_AVAILABLE = False
        return False


def _statements(sql: str) -> list[str]:
    """Split trusted migration SQL without using executescript's implicit commit."""
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                statements.append(statement)
            buffer = ""
    if buffer.strip():
        raise sqlite3.OperationalError("incomplete SQL statement in migration")
    return statements


def _apply_migration(conn: sqlite3.Connection, sql: str) -> None:
    global FTS_AVAILABLE
    main_sql, fts_sql = _split_fts(sql)
    for statement in _statements(main_sql):
        conn.execute(statement)
        if "DROP TABLE IF EXISTS spans_fts" in statement:
            FTS_AVAILABLE = False
    if fts_sql is not None:
        _try_create_fts(conn, fts_sql)


def _database_path(conn: sqlite3.Connection) -> Path | None:
    row = conn.execute("PRAGMA database_list").fetchone()
    if row is None or not row[2]:
        return None
    return Path(str(row[2])).resolve()


def _has_user_data_schema(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """SELECT 1 FROM sqlite_master
           WHERE type = 'table' AND name NOT LIKE 'sqlite_%' AND name != '_migrations'
           LIMIT 1"""
    ).fetchone()
    return row is not None


def _verify_integrity(conn: sqlite3.Connection) -> None:
    result = conn.execute("PRAGMA quick_check").fetchone()
    if result is None or str(result[0]).lower() != "ok":
        detail = str(result[0]) if result else "no result"
        raise sqlite3.DatabaseError(f"database integrity check failed before migration: {detail}")


def _backup_before_migration(conn: sqlite3.Connection, next_version: str) -> Path | None:
    db_path = _database_path(conn)
    if db_path is None or not _has_user_data_schema(conn):
        return None
    _verify_integrity(conn)
    backup_dir = ensure_private_dir(db_path.parent / "backups" / "migrations")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    backup_path = backup_dir / f"{db_path.name}.pre-{next_version}-{stamp}.bak"
    ensure_private_file(backup_path)
    destination = sqlite3.connect(backup_path)
    try:
        conn.backup(destination)
        result = destination.execute("PRAGMA quick_check").fetchone()
        if result is None or str(result[0]).lower() != "ok":
            raise sqlite3.DatabaseError("migration backup integrity check failed")
    finally:
        destination.close()
    return backup_path


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply pending SQL migrations in filename order; skip already applied."""
    _ensure_migrations_table(conn)
    applied = _applied_versions(conn)
    newly_applied: list[str] = []
    pending = [
        path for path in sorted(_migrations_path().glob("*.sql")) if path.stem not in applied
    ]
    if not pending:
        return []
    _backup_before_migration(conn, pending[0].stem)

    for path in pending:
        version = path.stem
        try:
            conn.execute("BEGIN IMMEDIATE")
            _apply_migration(conn, path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO _migrations (version, applied_at) VALUES (?, ?)",
                (version, datetime.now(UTC).isoformat()),
            )
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
        newly_applied.append(version)

    return newly_applied
