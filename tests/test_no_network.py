"""Default local product journeys must not attempt outbound connections."""

from __future__ import annotations

import socket
from pathlib import Path

from fastapi.testclient import TestClient

from server.app import create_app
from server.config import Settings
from server.demo.seed import seed_demo_workspace
from server.export.static import export_static_snapshot
from server.util.egress import egress_status


def test_default_health_demo_and_static_export_make_no_network_attempt(
    tmp_path: Path, monkeypatch
) -> None:
    attempts: list[object] = []

    def deny_connect(_socket: socket.socket, address: object) -> None:
        attempts.append(address)
        raise AssertionError(f"unexpected network attempt: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", deny_connect)
    workspace = tmp_path / "workspace"
    seed_demo_workspace(workspace, reset=True)

    static_dir = tmp_path / "static"
    (static_dir / "assets").mkdir(parents=True)
    (static_dir / "assets" / "app.js").write_text("", encoding="utf-8")
    (static_dir / "index.html").write_text(
        '<!doctype html><html><head><script src="/assets/app.js"></script></head>'
        '<body><div id="root"></div></body></html>',
        encoding="utf-8",
    )
    monkeypatch.setenv("CAIRN_STATIC_DIR", str(static_dir))

    client = TestClient(create_app(Settings(workspace_root=workspace, static_dir=static_dir)))
    assert client.get("/api/health").status_code == 200
    export_static_snapshot(workspace, tmp_path / "export")

    assert attempts == []
    assert egress_status(workspace)["entry_count"] == 0
