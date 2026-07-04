"""API /api/config GET+POST round-trip against ~/.config/cairn/config.toml."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import cairn.config as cfgmod
from cairn.live.server import LiveServer


def _patch_config(tmp_path: Path, monkeypatch) -> Path:
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "config.toml"
    monkeypatch.setattr(cfgmod, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cfgmod, "CONFIG_PATH", cfg_file)
    return cfg_file


def test_api_config_get_returns_shape(tmp_path: Path, monkeypatch) -> None:
    _patch_config(tmp_path, monkeypatch)
    server = LiveServer(tmp_path, port=18791)
    server.serve_background()
    try:
        with urlopen(f"{server.base_url}/api/config") as resp:
            data = json.loads(resp.read())
        assert "config" in data
        assert isinstance(data["config"], dict)
        assert "data_notes" in data
    finally:
        server.shutdown()


def test_api_config_post_round_trips(tmp_path: Path, monkeypatch) -> None:
    cfg_file = _patch_config(tmp_path, monkeypatch)
    server = LiveServer(tmp_path, port=18792)
    server.serve_background()
    try:
        body = json.dumps({"optimize": {"auto": True}, "budgets": {"daily_usd": 5.0}}).encode()
        req = Request(
            f"{server.base_url}/api/config",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as resp:
            posted = json.loads(resp.read())
        assert posted["ok"] is True

        with urlopen(f"{server.base_url}/api/config") as resp:
            data = json.loads(resp.read())
        assert data["config"]["optimize"]["auto"] is True
        assert float(data["config"]["budgets"]["daily_usd"]) == 5.0
        assert cfg_file.is_file()
    finally:
        server.shutdown()


def test_api_config_post_rejects_invalid_keys(tmp_path: Path, monkeypatch) -> None:
    _patch_config(tmp_path, monkeypatch)
    server = LiveServer(tmp_path, port=18793)
    server.serve_background()
    try:
        body = json.dumps({"nonsense": {"x": 1}}).encode()
        req = Request(
            f"{server.base_url}/api/config",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urlopen(req)
        except HTTPError as exc:
            assert exc.code == 400
            data = json.loads(exc.read())
            assert data["ok"] is False
        else:
            raise AssertionError("expected 400 for invalid section")
    finally:
        server.shutdown()


def test_config_round_trips_toml(tmp_path: Path, monkeypatch) -> None:
    _patch_config(tmp_path, monkeypatch)
    cfgmod.save_config_dict({"optimize": {"auto": True}, "limits": {"five_hour_tokens": 12345}})
    loaded = cfgmod.load_config_dict()
    assert loaded["optimize"]["auto"] is True
    assert loaded["limits"]["five_hour_tokens"] == 12345
