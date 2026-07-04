"""§6.1 action registry parity — CLI, API manifest, and POST surfaces."""

from __future__ import annotations

import subprocess
import sys

from fastapi.testclient import TestClient

from server.api.actions import build_manifest, get_action

EXPECTED_ACTIONS = {
    "sync",
    "backfill",
    "rebuild_view",
    "check",
    "export_bundle",
    "mcp_install",
    "optimize_propose",
    "experiment_apply",
    "experiment_revert",
    "experiment_measure",
    "insight_set_state",
    "annotate",
    "workspace_scan",
    "config_set",
    "server_stop",
}


def test_registry_has_exact_actions() -> None:
    names = {item.name for item in build_manifest()}
    assert names == EXPECTED_ACTIONS


def test_every_action_has_handler() -> None:
    for name in EXPECTED_ACTIONS:
        assert get_action(name) is not None


def test_api_manifest_matches_registry(api_client: TestClient) -> None:
    resp = api_client.get("/api/actions")
    names = {item["name"] for item in resp.json()["actions"]}
    assert names == EXPECTED_ACTIONS


def test_every_action_postable(api_client: TestClient) -> None:
    skip_payload = {
        "experiment_apply": {"experiment_id": "missing"},
        "experiment_revert": {"experiment_id": "missing"},
        "experiment_measure": {"experiment_id": "missing"},
        "insight_set_state": {"insight_id": "missing", "state": "ack"},
        "annotate": {"trace_id": "missing", "text": "note"},
        "rebuild_view": {"view": "usage"},
        "config_set": {"key": "host", "value": "127.0.0.1"},
    }
    for name in EXPECTED_ACTIONS:
        if name == "server_stop":
            continue
        payload = skip_payload.get(name, {})
        resp = api_client.post(f"/api/actions/{name}", json=payload)
        assert resp.status_code in {200, 400}, f"{name} -> {resp.status_code}"


def test_cli_help_lists_core_commands() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "server.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    for cmd in ("ui", "sync", "check", "show", "traces", "insights", "optimize", "action"):
        assert cmd in result.stdout


def test_cli_action_subcommands_cover_registry() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "server.cli", "action", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    for name in EXPECTED_ACTIONS:
        assert name in result.stdout


def test_cli_aliases_exist() -> None:
    for alias in ("sync", "check", "optimize"):
        result = subprocess.run(
            [sys.executable, "-m", "server.cli", alias, "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, alias
