"""Typed configuration precedence, mutation, redaction, and runtime parity."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server.configuration as configuration
from scripts.generate_config_reference import OUTPUT, configuration_reference_markdown
from server.analyze.outcome_tests import test_command_for as configured_test_command_for
from server.config import Settings
from server.configuration import (
    ConfigError,
    get_config_value,
    list_config_values,
    load_config,
    mutate_config,
)
from server.ingest.pricing import estimate_cost, load_overrides


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    user = tmp_path / "home" / ".config" / "cairn" / "config.toml"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(configuration, "USER_CONFIG_PATH", user)
    monkeypatch.setattr("server.util.user_config.CONFIG_PATH", user)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for name in configuration.ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    return user, workspace


def test_precedence_is_cli_then_environment_then_workspace_then_user(
    isolated_config: tuple[Path, Path],
) -> None:
    user, workspace = isolated_config
    user.parent.mkdir(parents=True)
    user.write_text('[server]\nport = 8001\nhost = "user"\n', encoding="utf-8")
    local = configuration.workspace_config_path(workspace)
    local.parent.mkdir(parents=True)
    local.write_text('[server]\nport = 8002\nhost = "workspace"\n', encoding="utf-8")

    workspace_value = load_config(workspace, environ={})
    assert workspace_value.server.port == 8002
    assert workspace_value.server.host == "workspace"

    environment_value = load_config(
        workspace, environ={"CAIRN_PORT": "8003", "CAIRN_HOST": "environment"}
    )
    assert environment_value.server.port == 8003
    assert environment_value.server.host == "environment"

    cli_value = load_config(
        workspace,
        environ={"CAIRN_PORT": "8003"},
        cli_overrides={"port": 8004},
    )
    assert cli_value.server.port == 8004


def test_settings_uses_same_file_and_environment_contract(
    isolated_config: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    user, workspace = isolated_config
    user.parent.mkdir(parents=True)
    user.write_text("[server]\nport = 8123\n", encoding="utf-8")
    monkeypatch.setenv("CAIRN_PORT", "8124")
    assert Settings(workspace_root=workspace).port == 8124
    assert Settings(port=8125, workspace_root=workspace).port == 8125


def test_atomic_set_and_unset_preserve_comments_and_unrelated_keys(
    isolated_config: tuple[Path, Path],
) -> None:
    user, workspace = isolated_config
    user.parent.mkdir(parents=True)
    user.write_text(
        '# owner comment\n[server]\nhost = "127.0.0.1" # keep inline\n\n'
        "[budgets]\nweekly_usd = 25 # untouched\n",
        encoding="utf-8",
    )

    result = mutate_config("set", "port", value="9010", workspace_root=workspace)
    assert result["key"] == "server.port"
    text = user.read_text(encoding="utf-8")
    assert "# owner comment" in text
    assert 'host = "127.0.0.1" # keep inline' in text
    assert "weekly_usd = 25 # untouched" in text
    assert "port = 9010" in text
    if os.name != "nt":
        assert user.stat().st_mode & 0o777 == 0o600

    mutate_config("unset", "server.port", workspace_root=workspace)
    assert "port = 9010" not in user.read_text(encoding="utf-8")


def test_invalid_or_unknown_mutation_is_actionable_and_does_not_write(
    isolated_config: tuple[Path, Path],
) -> None:
    user, workspace = isolated_config
    with pytest.raises(ConfigError, match="Unknown configuration key"):
        mutate_config("set", "server.nope", value="1", workspace_root=workspace)
    assert not user.exists()

    with pytest.raises(ConfigError, match="server.port"):
        mutate_config("set", "server.port", value="not-a-port", workspace_root=workspace)
    assert not user.exists()


def test_get_and_list_redact_secrets_and_report_sources(
    isolated_config: tuple[Path, Path],
) -> None:
    user, workspace = isolated_config
    user.parent.mkdir(parents=True)
    user.write_text('[server]\ntoken = "private-token"\n', encoding="utf-8")

    item = get_config_value("token", workspace)
    assert item == {
        "key": "server.token",
        "value": "<redacted>",
        "source": "user",
        "secret": True,
    }
    revealed = get_config_value("server.token", workspace, reveal_secrets=True)
    assert revealed["value"] == "private-token"
    listed = {row["key"]: row for row in list_config_values(workspace)}
    assert listed["server.token"]["value"] == "<redacted>"


def test_aliases_and_documented_sections_change_runtime_consumers(
    isolated_config: tuple[Path, Path],
) -> None:
    user, workspace = isolated_config
    user.parent.mkdir(parents=True)
    user.write_text(
        """
five_hour_tokens = 4321
test_command = "pytest -q"

[diagnose]
cascade_k = 9

[optimize]
backend = "codex-cli"

[mcp]
auto_install = true

[pricing.overrides.gpt-test]
input_per_mtok = 2.0
output_per_mtok = 4.0
""".lstrip(),
        encoding="utf-8",
    )

    resolved = load_config(workspace, environ={})
    assert resolved.limits.five_hour_tokens == 4321
    assert resolved.tests["default"] == "pytest -q"
    assert resolved.diagnose.cascade_k == 9
    assert resolved.optimize.backend == "codex-cli"
    assert resolved.mcp.auto_install is True
    assert configured_test_command_for(None) == "pytest -q"

    overrides = load_overrides(workspace)
    assert overrides["gpt-test"]["input_per_mtok"] == 2.0
    priced = estimate_cost(
        "gpt-test",
        {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
        root=workspace,
    )
    assert priced.total == 6.0


def test_legacy_top_level_server_alias_migrates_in_memory(
    isolated_config: tuple[Path, Path],
) -> None:
    user, workspace = isolated_config
    user.parent.mkdir(parents=True)
    user.write_text('host = "localhost"\nport = 9090\n', encoding="utf-8")
    resolved = load_config(workspace, environ={})
    assert resolved.server.host == "localhost"
    assert resolved.server.port == 9090


def test_generated_configuration_reference_is_current() -> None:
    assert OUTPUT.read_text(encoding="utf-8") == configuration_reference_markdown()


def test_configuration_action_has_get_set_unset_list_parity(
    api_client: TestClient, api_workspace: tuple[Path, str, str]
) -> None:
    workspace, _workspace_id, _trace_id = api_workspace
    set_response = api_client.post(
        "/api/actions/config_set",
        json={
            "operation": "set",
            "key": "budgets.weekly_usd",
            "value": "12.5",
            "scope": "workspace",
        },
    )
    assert set_response.status_code == 200
    assert set_response.json()["result"]["value"] == 12.5
    assert (workspace / ".cairn" / "config.toml").is_file()

    get_response = api_client.post(
        "/api/actions/config_set",
        json={"operation": "get", "key": "budgets.weekly_usd"},
    )
    assert get_response.json()["result"] == {
        "key": "budgets.weekly_usd",
        "value": 12.5,
        "source": "workspace",
        "secret": False,
    }

    list_response = api_client.post(
        "/api/actions/config_set",
        json={"operation": "list"},
    )
    values = {row["key"]: row for row in list_response.json()["result"]["values"]}
    assert values["budgets.weekly_usd"]["source"] == "workspace"
    assert values["server.token"]["value"] is None

    unset_response = api_client.post(
        "/api/actions/config_set",
        json={
            "operation": "unset",
            "key": "budgets.weekly_usd",
            "scope": "workspace",
        },
    )
    assert unset_response.status_code == 200
    assert get_config_value("budgets.weekly_usd", workspace)["value"] is None

    invalid = api_client.post(
        "/api/actions/config_set",
        json={
            "operation": "set",
            "key": "server.unknown",
            "value": "x",
            "scope": "workspace",
        },
    )
    assert invalid.status_code == 400
    assert "Unknown configuration key" in invalid.json()["error"]["message"]


def test_budget_and_mcp_config_change_registered_action_behavior(
    api_client: TestClient, api_workspace: tuple[Path, str, str]
) -> None:
    workspace, _workspace_id, trace_id = api_workspace
    with sqlite3.connect(workspace / ".cairn" / "cairn.db") as conn:
        conn.execute("UPDATE outcomes SET quality_score = 0.2 WHERE trace_id = ?", (trace_id,))
    for key, value in (("budgets.min_quality", "0.9"), ("mcp.client", "other")):
        response = api_client.post(
            "/api/actions/config_set",
            json={
                "operation": "set",
                "key": key,
                "value": value,
                "scope": "workspace",
            },
        )
        assert response.status_code == 200

    check = api_client.post("/api/actions/check", json={})
    assert check.status_code == 200
    assert check.json()["result"]["ok"] is False
    assert "quality 0.2" in check.json()["result"]["failures"][0]

    mcp = api_client.post("/api/actions/mcp_install", json={})
    assert mcp.status_code == 200
    assert mcp.json()["result"]["client"] == "other"
    assert mcp.json()["result"]["written"] is False
