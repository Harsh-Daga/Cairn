"""§6.1 action registry parity — CLI, API manifest, and POST surfaces."""

from __future__ import annotations

import subprocess
import sys

from fastapi.testclient import TestClient

from server.api.actions import build_manifest, get_action

EXPECTED_ACTIONS = {
    "annotate",
    "archive_export",
    "archive_import",
    "archive_inspect",
    "backfill",
    "check",
    "circuit_resume",
    "circuit_status",
    "config_set",
    "corrections_rebuild",
    "db_backup",
    "db_backup_list",
    "db_compact",
    "db_integrity",
    "db_restore",
    "demo_seed",
    "egress_export",
    "egress_status",
    "experiment_apply",
    "experiment_measure",
    "experiment_revert",
    "export_bundle",
    "export_session_html",
    "git_exclude_cairn",
    "insight_set_state",
    "insight_snooze",
    "lifecycle_cleanup",
    "lifecycle_plan",
    "mcp_install",
    "optimize_evaluate",
    "optimize_propose",
    "pricing_refresh_preview",
    "pricing_status",
    "rebuild_view",
    "reflector_preview",
    "reflector_run",
    "regression_create",
    "regression_delete",
    "regression_export",
    "regression_import",
    "regression_run",
    "regression_compare",
    "server_stop",
    "source_drift_status",
    "storage_strip",
    "sync",
    "verification_rebuild",
    "workspace_scan",
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
        "insight_snooze": {"insight_id": "missing", "days": 14},
        "annotate": {"trace_id": "missing", "text": "note"},
        "rebuild_view": {"view": "usage"},
        "config_set": {
            "operation": "set",
            "key": "host",
            "value": "127.0.0.1",
            "scope": "workspace",
        },
        "reflector_preview": {"backend": "test-cli"},
        "reflector_run": {
            "backend": "test-cli",
            "consent_token": "0" * 64,
        },
        "regression_create": {"trace_id": "missing"},
        "regression_delete": {"regression_id": "missing"},
        "regression_export": {"regression_id": "missing"},
        "regression_import": {"archive_path": "missing.zip"},
        "regression_run": {"regression_id": "missing", "trace_id": "missing"},
        "regression_compare": {"regression_id": "missing"},
        "archive_export": {"mode": "scrubbed", "dry_run": True},
        "archive_import": {"archive_path": "missing.zip", "dry_run": True},
        "archive_inspect": {"archive_path": "missing.zip"},
        "export_session_html": {"trace_id": "missing"},
        "db_restore": {"backup_path": "missing.bak", "confirm": False},
        "lifecycle_cleanup": {"dry_run": True},
        "storage_strip": {"dry_run": True},
    }
    for name in EXPECTED_ACTIONS:
        if name in {"server_stop", "demo_seed"}:
            continue
        payload = skip_payload.get(name, {})
        resp = api_client.post(f"/api/actions/{name}", json=payload)
        assert resp.status_code in {200, 400, 422}, f"{name} -> {resp.status_code}"


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


def test_cli_config_surface_has_complete_mutation_contract() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "server.cli", "config", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    for command in ("get", "set", "unset", "list"):
        assert command in result.stdout
