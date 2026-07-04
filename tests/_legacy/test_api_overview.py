"""API overview endpoint shape."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from cairn.ledger.schema import migrate
from cairn.live.server import LiveServer


def test_api_overview_shape(tmp_path: Path) -> None:
    cairn = tmp_path / ".cairn"
    cairn.mkdir()
    conn = sqlite3.connect(cairn / "ledger.db")
    migrate(conn)
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO runs (
          run_id, source, external_id, project, started_at, status,
          total_input_tokens, total_output_tokens, total_cost, has_cost, event_count
        ) VALUES ('run-1', 'claude-code', 'ext-1', 'proj', ?, 'completed', 1000, 200, 0.5, 1, 5)
        """,
        (now,),
    )
    conn.commit()
    conn.close()

    server = LiveServer(tmp_path, port=18787)
    server.serve_background()
    try:
        with urlopen(f"{server.base_url}/api/overview?days=30") as resp:
            data = json.loads(resp.read())
        assert "summary" in data
        assert "kpis" in data
        assert data["summary"]["sessions"] == 1
        assert data["project_name"] == tmp_path.name
        assert "data_notes" in data
    finally:
        server.shutdown()
