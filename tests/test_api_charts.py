"""Charts API returns sparse-friendly structure."""

from __future__ import annotations

import json
import socket
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from cairn.ledger.schema import migrate
from cairn.live.server import LiveServer


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_api_charts_shape(tmp_path: Path) -> None:
    cairn = tmp_path / ".cairn"
    cairn.mkdir()
    conn = sqlite3.connect(cairn / "ledger.db")
    migrate(conn)
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    conn.execute(
        """
        INSERT INTO rollup_daily (
          day, project, source, model, sessions, cost_total, input_tokens, output_tokens,
          has_cost_sessions
        ) VALUES (?, 'p', 'claude-code', 'claude-sonnet', 1, 1.5, 1000, 200, 1)
        """,
        (day,),
    )
    conn.commit()
    conn.close()

    server = LiveServer(tmp_path, port=_free_port())
    server.serve_background()
    try:
        with urlopen(f"{server.base_url}/api/charts?days=30") as resp:
            data = json.loads(resp.read())
        assert "daily_cost" in data
        assert "waste_by_category" in data
        if data["daily_cost"]:
            assert "by_model" in data["daily_cost"][0]
    finally:
        server.shutdown()
