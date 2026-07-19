"""Persisted verification receipt repository."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


class ReceiptRepo:
    @staticmethod
    def upsert(conn: sqlite3.Connection, receipt: dict[str, Any], *, built_at: str) -> None:
        conn.execute(
            """
            INSERT INTO verification_receipts (
              trace_id, schema_version, builder_version, status, debt_score,
              content_hash, receipt_json, built_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trace_id) DO UPDATE SET
              schema_version=excluded.schema_version,
              builder_version=excluded.builder_version,
              status=excluded.status,
              debt_score=excluded.debt_score,
              content_hash=excluded.content_hash,
              receipt_json=excluded.receipt_json,
              built_at=excluded.built_at
            """,
            (
                str(receipt["trace_id"]),
                str(receipt["schema_version"]),
                str(receipt["builder_version"]),
                str(receipt["status"]),
                float(receipt["debt"]["score"]),
                str(receipt["content_hash"]),
                json.dumps(receipt, sort_keys=True, separators=(",", ":")),
                built_at,
            ),
        )

    @staticmethod
    def get(conn: sqlite3.Connection, trace_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT receipt_json FROM verification_receipts WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
        if row is None:
            return None
        loaded = json.loads(str(row["receipt_json"]))
        if not isinstance(loaded, dict):
            return None
        return loaded

    @staticmethod
    def get_hash(conn: sqlite3.Connection, trace_id: str) -> str | None:
        row = conn.execute(
            "SELECT content_hash FROM verification_receipts WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
        return str(row["content_hash"]) if row is not None else None
