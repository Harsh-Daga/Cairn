"""Import cairn.archive.v1 ZIP with dry-run and conflict policies."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Literal

from server.archive.inspect_archive import inspect_archive
from server.archive.safe_zip import ArchiveZipError, safe_read_members
from server.archive.schema import ARCHIVE_SCHEMA_VERSION, SUPPORTED_READ_SCHEMAS

ConflictMode = Literal["skip", "replace", "fail"]


def import_archive(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    workspace_root: Path,
    archive: Path,
    dry_run: bool = True,
    conflict: ConflictMode = "fail",
) -> dict[str, Any]:
    """Import archive domains into the local DB.

    Default is dry-run. Source agent logs are never touched.
    """
    _ = workspace_root  # reserved for future path rewriting / scrub-on-import
    inspection = inspect_archive(archive)
    if not inspection.get("ok"):
        return inspection
    if not inspection.get("supported"):
        return {
            "ok": False,
            "error": "unsupported_schema",
            "schema": inspection.get("schema"),
            "supported_read_schemas": sorted(SUPPORTED_READ_SCHEMAS),
        }
    if inspection.get("checksum_mismatches"):
        return {
            "ok": False,
            "error": "checksum_mismatch",
            "mismatches": inspection["checksum_mismatches"],
        }

    try:
        members = safe_read_members(archive)
    except ArchiveZipError as exc:
        return {"ok": False, "error": "import_rejected", "detail": str(exc)}

    traces = json.loads(members["traces.json"].decode("utf-8")).get("rows") or []
    spans = json.loads(members["spans.json"].decode("utf-8")).get("rows") or []
    links = json.loads(members["span_links.json"].decode("utf-8")).get("rows") or []
    outcomes = json.loads(members["outcomes.json"].decode("utf-8")).get("rows") or []
    quality = json.loads(members["data_quality.json"].decode("utf-8")).get("rows") or []
    diagnostics = json.loads(members["diagnostics.json"].decode("utf-8")).get("rows") or []
    receipts = json.loads(members["verification_receipts.json"].decode("utf-8")).get("rows") or []
    corrections = json.loads(members["session_corrections.json"].decode("utf-8")).get("rows") or []

    would_insert = 0
    would_replace = 0
    would_skip = 0
    conflicts: list[str] = []
    for trace in traces:
        tid = str(trace.get("trace_id") or "")
        if not tid:
            continue
        exists = conn.execute("SELECT 1 FROM traces WHERE trace_id = ?", (tid,)).fetchone()
        if exists:
            conflicts.append(tid)
            if conflict == "skip":
                would_skip += 1
            elif conflict == "replace":
                would_replace += 1
            else:
                would_skip += 0  # fail path counted below
        else:
            would_insert += 1

    plan = {
        "schema": ARCHIVE_SCHEMA_VERSION,
        "dry_run": dry_run,
        "conflict": conflict,
        "traces_in_archive": len(traces),
        "would_insert": would_insert,
        "would_replace": would_replace if conflict == "replace" else 0,
        "would_skip": (
            would_skip if conflict == "skip" else (len(conflicts) if conflict == "fail" else 0)
        ),
        "conflict_ids_sample": conflicts[:20],
        "source_logs_untouched": True,
        "inspect": {
            "mode": inspection.get("mode"),
            "producer_version": inspection.get("producer_version"),
            "trace_count": inspection.get("trace_count"),
        },
    }
    if dry_run:
        ok = not (conflict == "fail" and conflicts)
        return {
            "ok": ok,
            **plan,
            "error": "conflict" if not ok else None,
            "message": (
                "Conflicts present; pass conflict=skip|replace to apply." if not ok else None
            ),
            "limitation": "Dry-run only — no rows written.",
        }
    if conflict == "fail" and conflicts:
        return {
            "ok": False,
            "error": "conflict",
            **plan,
            "message": "Pass conflict=skip|replace after reviewing dry-run.",
        }

    inserted = 0
    replaced = 0
    skipped = 0
    partial: list[dict[str, str]] = []
    for trace in traces:
        tid = str(trace.get("trace_id") or "")
        if not tid:
            continue
        exists = conn.execute("SELECT 1 FROM traces WHERE trace_id = ?", (tid,)).fetchone()
        if exists and conflict == "skip":
            skipped += 1
            continue
        if exists and conflict == "replace":
            _delete_trace_children(conn, tid)
            conn.execute("DELETE FROM traces WHERE trace_id = ?", (tid,))
            replaced += 1
        elif exists:
            skipped += 1
            continue
        else:
            inserted += 1
        try:
            _upsert_trace(conn, workspace_id, trace)
        except sqlite3.Error as exc:
            partial.append({"trace_id": tid, "error": str(exc)})

    span_by_trace: dict[str, list[dict[str, Any]]] = {str(s.get("trace_id")): [] for s in spans}
    for span in spans:
        span_by_trace.setdefault(str(span.get("trace_id")), []).append(span)

    applied_ids = {
        str(t["trace_id"])
        for t in traces
        if str(t.get("trace_id") or "")
        and (str(t["trace_id"]) not in conflicts or conflict == "replace")
        and not (str(t["trace_id"]) in conflicts and conflict == "skip")
    }
    for tid in applied_ids:
        for span in span_by_trace.get(tid, []):
            _upsert_span(conn, span)
    for link in links:
        _upsert_link(conn, link)
    for table, rows in (
        ("outcomes", outcomes),
        ("data_quality", quality),
        ("diagnostics", diagnostics),
        ("verification_receipts", receipts),
        ("session_corrections", corrections),
    ):
        if not _table_exists(conn, table):
            continue
        for row in rows:
            if str(row.get("trace_id")) not in applied_ids:
                continue
            _upsert_by_trace(conn, table, row)

    return {
        "ok": len(partial) == 0,
        **plan,
        "dry_run": False,
        "inserted": inserted,
        "replaced": replaced,
        "skipped": skipped,
        "partial_failures": partial,
        "limitation": (
            "Policy JSON is not auto-applied to config.toml (inspect-only on import). "
            "Partial failures leave earlier successful traces applied."
            if partial
            else "Policy snapshot is not auto-applied; review policy.json manually."
        ),
    }


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (name,),
        ).fetchone()
        is not None
    )


def _delete_trace_children(conn: sqlite3.Connection, trace_id: str) -> None:
    if _table_exists(conn, "span_links"):
        conn.execute(
            """
            DELETE FROM span_links WHERE from_span_id IN (
              SELECT span_id FROM spans WHERE trace_id = ?
            ) OR to_span_id IN (
              SELECT span_id FROM spans WHERE trace_id = ?
            )
            """,
            (trace_id, trace_id),
        )
    for table in (
        "spans",
        "outcomes",
        "data_quality",
        "diagnostics",
        "verification_receipts",
        "session_corrections",
        "mcp_consultations",
        "fingerprints",
    ):
        if _table_exists(conn, table):
            conn.execute(f"DELETE FROM {table} WHERE trace_id = ?", (trace_id,))


def _upsert_trace(conn: sqlite3.Connection, workspace_id: str, row: dict[str, Any]) -> None:
    cols = [c[1] for c in conn.execute("PRAGMA table_info(traces)").fetchall()]
    data = {k: v for k, v in row.items() if k in cols}
    data["workspace_id"] = workspace_id
    keys = list(data.keys())
    conn.execute(
        f"INSERT INTO traces ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})",
        tuple(data[k] for k in keys),
    )


def _upsert_span(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    cols = [c[1] for c in conn.execute("PRAGMA table_info(spans)").fetchall()]
    data = {k: v for k, v in row.items() if k in cols}
    if "span_id" not in data:
        return
    keys = list(data.keys())
    conn.execute(
        f"INSERT OR REPLACE INTO spans ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})",
        tuple(data[k] for k in keys),
    )


def _upsert_link(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    if not _table_exists(conn, "span_links"):
        return
    conn.execute(
        """
        INSERT OR IGNORE INTO span_links (from_span_id, to_span_id, link_type)
        VALUES (?, ?, ?)
        """,
        (row.get("from_span_id"), row.get("to_span_id"), row.get("link_type")),
    )


def _upsert_by_trace(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    data = {k: v for k, v in row.items() if k in cols}
    if "trace_id" not in data:
        return
    keys = list(data.keys())
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({', '.join(keys)}) "
        f"VALUES ({', '.join('?' for _ in keys)})",
        tuple(data[k] for k in keys),
    )
