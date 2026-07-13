from __future__ import annotations

import sys

from typer.testing import CliRunner

from server.cli import app
from server.update import PACKAGE_NAME, upgrade_command


def test_upgrade_prefers_uv() -> None:
    assert upgrade_command(lambda name: "/bin/uv" if name == "uv" else None) == (
        "uv tool",
        ["uv", "tool", "upgrade", PACKAGE_NAME],
    )


def test_upgrade_falls_back_to_current_python() -> None:
    method, command = upgrade_command(lambda _name: None)
    assert method == "pip"
    assert command[:3] == [sys.executable, "-m", "pip"]


def test_upgrade_check_is_non_mutating() -> None:
    result = CliRunner().invoke(app, ["upgrade", "--check"])
    assert result.exit_code == 0
    assert "Updating Cairn via" in result.output
