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


def test_token_protects_exposed_server_and_bootstraps_browser_cookie() -> None:
    client = TestClient(create_app(Settings(host="0.0.0.0", token="secret")))

    denied = client.get("/api/health")
    assert denied.status_code == 401
    assert denied.headers["www-authenticate"] == "Bearer"

    bearer = client.get("/api/health", headers={"Authorization": "Bearer secret"})
    assert bearer.status_code == 200

    browser = client.get("/?token=secret", follow_redirects=False)
    assert browser.status_code == 307
    assert browser.headers["location"] == "/"
    assert "cairn_token" in browser.headers["set-cookie"]

    client.cookies.set("cairn_token", "secret")
    assert client.get("/api/health").status_code == 200
