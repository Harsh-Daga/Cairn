"""App lifespan and live ingest wiring."""

from __future__ import annotations

from fastapi.testclient import TestClient

from server.app import create_app
from server.config import Settings


def test_lifespan_starts_ingest_pipeline(tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    settings = Settings(workspace_root=root)
    application = create_app(settings)
    with TestClient(application) as client:
        runtime = client.app.state.runtime
        assert runtime.pipeline._watcher._thread is not None
        assert runtime.pipeline._watcher._thread.is_alive()
