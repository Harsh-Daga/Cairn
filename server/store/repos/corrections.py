"""Persisted session corrections and local relabels."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


class CorrectionRepo:
    @staticmethod
    def upsert(conn: sqlite3.Connection, payload: dict[str, Any], *, built_at: str) -> None:
        conn.execute(
            """
            INSERT INTO session_corrections (
              trace_id, schema_version, builder_version, correction_count,
              unresolved_count, content_hash, corrections_json, built_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trace_id) DO UPDATE SET
              schema_version=excluded.schema_version,
              builder_version=excluded.builder_version,
              correction_count=excluded.correction_count,
              unresolved_count=excluded.unresolved_count,
              content_hash=excluded.content_hash,
              corrections_json=excluded.corrections_json,
              built_at=excluded.built_at
            """,
            (
                str(payload["trace_id"]),
                str(payload["schema_version"]),
                str(payload["builder_version"]),
                int(payload["correction_count"]),
                int(payload["unresolved_count"]),
                str(payload["content_hash"]),
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
                built_at,
            ),
        )

    @staticmethod
    def get(conn: sqlite3.Connection, trace_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT corrections_json FROM session_corrections WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
        if row is None:
            return None
        loaded = json.loads(str(row["corrections_json"]))
        return loaded if isinstance(loaded, dict) else None

    @staticmethod
    def get_hash(conn: sqlite3.Connection, trace_id: str) -> str | None:
        row = conn.execute(
            "SELECT content_hash FROM session_corrections WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
        return str(row["content_hash"]) if row is not None else None

    @staticmethod
    def list_relabels(conn: sqlite3.Connection, trace_id: str) -> dict[str, dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT correction_id, original_class, relabel_class, note, labeled_at
            FROM correction_relabels WHERE trace_id = ?
            """,
            (trace_id,),
        ).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            out[str(row["correction_id"])] = {
                "original_class": str(row["original_class"]),
                "relabel_class": str(row["relabel_class"]),
                "note": row["note"],
                "labeled_at": str(row["labeled_at"]),
            }
        return out

    @staticmethod
    def upsert_relabel(
        conn: sqlite3.Connection,
        *,
        correction_id: str,
        trace_id: str,
        original_class: str,
        relabel_class: str,
        note: str | None,
        labeled_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO correction_relabels (
              correction_id, trace_id, original_class, relabel_class, note, labeled_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(correction_id) DO UPDATE SET
              original_class=excluded.original_class,
              relabel_class=excluded.relabel_class,
              note=excluded.note,
              labeled_at=excluded.labeled_at
            """,
            (correction_id, trace_id, original_class, relabel_class, note, labeled_at),
        )
