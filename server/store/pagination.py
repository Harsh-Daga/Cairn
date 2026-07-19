"""Shared bounds and chunked row iteration for potentially large queries."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence

MAX_PAGE_SIZE = 1_000
MAX_PAGE_OFFSET = 1_000_000
DEFAULT_CHUNK_SIZE = 500
# Analytics aggregate builders may scan spans/traces; never materialize unbounded.
ANALYTICS_SPAN_CAP = 25_000
ANALYTICS_TRACE_CAP = 10_000
ANALYTICS_LINK_CAP = 5_000


def bounded_page(
    limit: int,
    offset: int = 0,
    *,
    max_limit: int = MAX_PAGE_SIZE,
) -> tuple[int, int]:
    """Validate repository pagination even when callers bypass the HTTP layer."""
    if limit < 1 or limit > max_limit:
        raise ValueError(f"limit must be between 1 and {max_limit}")
    if offset < 0 or offset > MAX_PAGE_OFFSET:
        raise ValueError(f"offset must be between 0 and {MAX_PAGE_OFFSET}")
    return limit, offset


def iter_rows(
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[object] = (),
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> Iterator[sqlite3.Row]:
    """Yield query rows in bounded batches instead of materializing the result."""
    bounded_page(chunk_size)
    cursor = conn.execute(sql, tuple(params))
    while rows := cursor.fetchmany(chunk_size):
        yield from rows


def fetch_capped(
    conn: sqlite3.Connection,
    sql: str,
    params: Sequence[object],
    *,
    cap: int,
) -> tuple[list[sqlite3.Row], int]:
    """Fetch at most ``cap`` rows; return (rows, total_matching_count).

    ``sql`` must not already include LIMIT. Count uses the same WHERE via a subquery.
    """
    if cap < 1:
        raise ValueError("cap must be >= 1")
    total_row = conn.execute(
        f"SELECT COUNT(*) AS n FROM ({sql})",
        tuple(params),
    ).fetchone()
    total = int(total_row["n"] or 0) if total_row is not None else 0
    rows = conn.execute(f"{sql} LIMIT ?", (*params, cap)).fetchall()
    return list(rows), total


def truncation_limitation(noun: str, sampled: int, total: int) -> str | None:
    """Human-readable note when an analytics sample is incomplete."""
    if total <= sampled:
        return None
    return (
        f"{noun} sampled the first {sampled:,} of {total:,} matching rows in range "
        "(ordered by session time); ledger ratios may be incomplete for larger workspaces."
    )
