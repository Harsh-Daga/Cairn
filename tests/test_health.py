"""Health endpoint tests."""

from __future__ import annotations

import pytest
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
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["content-security-policy"].startswith("default-src 'self'")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"


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
    cookie = browser.headers["set-cookie"]
    assert "cairn_token" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "secret" not in browser.headers["location"]
    assert browser.headers["cache-control"] == "no-store"

    client.cookies.set("cairn_token", "secret")
    assert client.get("/api/health").status_code == 200


def test_host_header_and_browser_origin_are_restricted() -> None:
    client = TestClient(create_app(Settings()))

    invalid_host = client.get("/api/health", headers={"Host": "attacker.example"})
    assert invalid_host.status_code == 400
    assert invalid_host.json()["error"]["code"] == "invalid_host"

    invalid_origin = client.post(
        "/v1/traces",
        headers={"Origin": "https://attacker.example"},
        content=b"{}",
    )
    assert invalid_origin.status_code == 403
    assert invalid_origin.json()["error"]["code"] == "invalid_origin"


def test_same_origin_preflight_is_explicit_and_remote_preflight_is_denied() -> None:
    client = TestClient(create_app(Settings()))
    local = client.options(
        "/v1/traces",
        headers={
            "Host": "127.0.0.1",
            "Origin": "http://127.0.0.1",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert local.status_code == 204
    assert local.headers["access-control-allow-origin"] == "http://127.0.0.1"
    assert "POST" in local.headers["access-control-allow-methods"]

    remote = client.options(
        "/v1/traces",
        headers={"Origin": "https://attacker.example"},
    )
    assert remote.status_code == 403


def test_query_token_cannot_authorize_mutation() -> None:
    client = TestClient(create_app(Settings(host="0.0.0.0", token="secret")))
    response = client.post("/v1/traces?token=secret", content=b"{}")
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/"),
        ("get", "/api/health"),
        ("get", "/api/live/events"),
        ("post", "/v1/traces"),
    ],
)
def test_token_covers_static_api_sse_and_otlp(method: str, path: str) -> None:
    client = TestClient(create_app(Settings(host="0.0.0.0", token="secret")))
    response = getattr(client, method)(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
