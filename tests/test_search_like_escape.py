"""Search LIKE patterns must treat %/_ as literals."""

from __future__ import annotations

import sqlite3
from zoneinfo import ZoneInfo

from server.api.payload_domains.common import day_key
from server.store.pagination import fetch_capped, truncation_limitation
from server.store.search import like_pattern


def test_like_pattern_escapes_metacharacters() -> None:
    assert like_pattern("a%b_c\\d") == r"%a\%b\_c\\d%"


def test_day_key_skips_null_and_garbage() -> None:
    zone = ZoneInfo("UTC")
    assert day_key(None, zone) is None
    assert day_key("", zone) is None
    assert day_key("not-a-date", zone) is None
    assert day_key("2026-07-18T12:00:00Z", zone) == "2026-07-18"


def test_fetch_capped_reports_total_and_truncation_note() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.executemany("INSERT INTO t(id) VALUES (?)", [(i,) for i in range(5)])
    rows, total = fetch_capped(conn, "SELECT id FROM t ORDER BY id", (), cap=2)
    assert total == 5
    assert [int(row["id"]) for row in rows] == [0, 1]
    note = truncation_limitation("Demo", len(rows), total)
    assert note is not None
    assert "2" in note and "5" in note
    assert truncation_limitation("Demo", 5, 5) is None
