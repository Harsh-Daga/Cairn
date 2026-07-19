"""Measure potential content-addressed deduplication without implementing CAS."""

from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter
from typing import Any

# Skip CAS for values where blob metadata (~digest+refcount row) dominates.
_MIN_INLINE_CHARS_FOR_CAS = 96


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def assess_content_dedup(
    conn: sqlite3.Connection, *, workspace_id: str | None = None
) -> dict[str, Any]:
    """Report hash reuse and rough inline-text savings if identical bodies shared one blob.

    Uses persisted ``text_hash`` when present; otherwise digests non-empty ``text_inline``
    so generated fixtures still produce a useful assessment. Does not mutate storage.
    """
    if workspace_id:
        rows = conn.execute(
            """
            SELECT s.text_inline, s.text_hash, s.args_hash
            FROM spans s
            JOIN traces t ON t.trace_id = s.trace_id
            WHERE t.workspace_id = ?
            """,
            (workspace_id,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT text_inline, text_hash, args_hash FROM spans").fetchall()

    span_count = len(rows)
    text_counter: Counter[str] = Counter()
    args_counter: Counter[str] = Counter()
    text_max_len: dict[str, int] = {}
    total_inline_chars = 0
    hashed_inline_chars = 0

    for row in rows:
        text = str(row["text_inline"] or "")
        total_inline_chars += len(text)
        text_hash = str(row["text_hash"] or "").strip()
        if not text_hash and len(text) >= _MIN_INLINE_CHARS_FOR_CAS:
            text_hash = _sha256_text(text)
        if text_hash:
            text_counter[text_hash] += 1
            text_max_len[text_hash] = max(text_max_len.get(text_hash, 0), len(text))
            hashed_inline_chars += len(text)
        args_hash = str(row["args_hash"] or "").strip()
        if args_hash:
            args_counter[args_hash] += 1

    with_text = sum(text_counter.values())
    distinct_text = len(text_counter)
    with_args = sum(args_counter.values())
    distinct_args = len(args_counter)
    unique_blob_chars = sum(text_max_len.values())
    rough_savings_chars = max(0, hashed_inline_chars - unique_blob_chars)
    reuse_ratio = round((with_text - distinct_text) / with_text, 4) if with_text else 0.0
    overhead_chars = distinct_text * 96
    net_savings_chars = rough_savings_chars - overhead_chars
    recommend_cas = net_savings_chars >= 1_000_000 and reuse_ratio >= 0.15

    return {
        "schema": "cairn.dedup_assessment.v1",
        "span_count": span_count,
        "text_hash": {
            "rows_with_hash": with_text,
            "distinct_hashes": distinct_text,
            "reuse_ratio": reuse_ratio,
            "duplicate_rows": max(0, with_text - distinct_text),
        },
        "args_hash": {
            "rows_with_hash": with_args,
            "distinct_hashes": distinct_args,
            "reuse_ratio": (
                round((with_args - distinct_args) / with_args, 4) if with_args else 0.0
            ),
            "duplicate_rows": max(0, with_args - distinct_args),
        },
        "inline_text": {
            "total_chars": total_inline_chars,
            "hashed_chars": hashed_inline_chars,
            "unique_blob_chars_estimate": unique_blob_chars,
            "rough_savings_chars": rough_savings_chars,
            "metadata_overhead_chars_estimate": overhead_chars,
            "net_savings_chars_estimate": net_savings_chars,
            "min_inline_chars_for_cas": _MIN_INLINE_CHARS_FOR_CAS,
        },
        "fts": {
            "spans_fts": False,
            "search_source": "canonical_spans_and_traces",
            "note": "spans_fts retired in migration 0007; no derived FTS index to rebuild.",
        },
        "recommendation": {
            "adopt_cas_in_1_2": False,
            "worthwhile_on_this_ledger": recommend_cas,
            "rationale": (
                "Adopt CAS only when net estimated savings exceed ~1 MiB characters and "
                "text-hash reuse is at least 15%. 1.2.0 keeps hashes + storage modes instead "
                "(ADR 0013)."
            ),
        },
        "limitation": (
            "When text_hash is missing, SHA-256 of text_inline (>=96 chars) is used for the "
            "assessment only. Compression CPU cost is not measured. Collision handling and "
            "refcount GC remain out of scope until CAS is adopted."
        ),
    }
