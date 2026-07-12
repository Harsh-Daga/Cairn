"""Health endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from server import __version__
from server.app import create_app
from server.config import Settings


def test_health_endpoint() -> None:
    settings = Settings(static_dir=Settings().static_dir)
    client = TestClient(create_app(settings))
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_loopback_bind_validation() -> None:
    settings = Settings(host="0.0.0.0", token=None)
    try:
        settings.validate_bind()
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_non_loopback_with_token_ok() -> None:
    settings = Settings(host="0.0.0.0", token="secret")
    settings.validate_bind()  # should not raise
