"""Session API payload shape."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from cairn.ledger.schema import migrate
from cairn.live.server import LiveServer


def test_api_session_shape(tmp_path: Path) -> None:
    cairn = tmp_path / ".cairn"
    cairn.mkdir()
    conn = sqlite3.connect(cairn / "ledger.db")
    migrate(conn)
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO runs (
          run_id, source, external_id, started_at, status, has_cost, event_count
        ) VALUES ('run-1', 'claude-code', 'ext-1', ?, 'completed', 1, 1)
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO events (run_id, seq, type, role, text_inline)
        VALUES ('run-1', 1, 'user_prompt', 'user', 'hello')
        """
    )
    conn.commit()
    conn.close()

    server = LiveServer(tmp_path, port=18788)
    server.serve_background()
    try:
        with urlopen(f"{server.base_url}/api/session/run-1") as resp:
            data = json.loads(resp.read())
        assert "run" in data
        assert "turns" in data
        assert "graph" in data
    finally:
        server.shutdown()
