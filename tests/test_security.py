"""Phase 19 security tests."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

from cairn.api.server import ApiServer
from cairn.security.audit import run_security_audit
from cairn.security.auth import authorize_bearer
from cairn.security.encrypt import decrypt_bytes, encrypt_bytes


def test_encrypt_round_trip() -> None:
    raw = b"secret bundle payload"
    encrypted = encrypt_bytes(raw, "test-passphrase")
    assert encrypted != raw
    assert decrypt_bytes(encrypted, "test-passphrase") == raw


def test_authorize_bearer() -> None:
    assert authorize_bearer(None, None) is True
    assert authorize_bearer("Bearer abc", "abc") is True
    assert authorize_bearer("Bearer wrong", "abc") is False


def test_security_audit_flags_inline_secret(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    secret = "sk-abcdefghijklmnopqrstuvwxyz1234"
    (root / "cairn.toml").write_text(f'api_key = "{secret}"\n', encoding="utf-8")
    findings = run_security_audit(root)
    codes = {f.code for f in findings}
    assert "config.inline_secret" in codes


def test_api_requires_token_when_configured(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CAIRN_API_TOKEN", "secret-token")
    repo = tmp_path / "proj"
    repo.mkdir()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    server = ApiServer(repo, port=port)
    server.serve_background()
    try:
        url = f"{server.base_url}/v1/openapi.json"
        try:
            with urllib.request.urlopen(url, timeout=3):
                raise AssertionError("expected unauthorized")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        request = urllib.request.Request(
            url,
            headers={"Authorization": "Bearer secret-token"},
        )
        with urllib.request.urlopen(request, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        assert payload["openapi"] == "3.0.3"
    finally:
        server.shutdown()
        monkeypatch.delenv("CAIRN_API_TOKEN", raising=False)
