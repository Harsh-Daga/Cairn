"""API /api/setup/scan returns detected agents + paths + counts."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from cairn.ledger.schema import migrate
from cairn.live.server import LiveServer


def test_api_setup_scan_returns_agents(tmp_path: Path) -> None:
    cairn = tmp_path / ".cairn"
    cairn.mkdir()
    conn = sqlite3.connect(cairn / "ledger.db")
    migrate(conn)
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO runs (run_id, source, external_id, started_at, status, event_count) "
        "VALUES ('r1', 'claude-code', 'e1', ?, 'completed', 3)",
        (now,),
    )
    conn.commit()
    conn.close()

    server = LiveServer(tmp_path, port=18794)
    server.serve_background()
    try:
        with urlopen(f"{server.base_url}/api/setup/scan") as resp:
            data = json.loads(resp.read())
        assert "agents" in data
        assert isinstance(data["agents"], list)
        assert "total_sessions" in data
        assert "data_notes" in data
    finally:
        server.shutdown()
