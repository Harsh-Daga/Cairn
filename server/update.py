"""Safe, explicit self-update support for installed Cairn CLIs."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable, Sequence

PACKAGE_NAME = "cairn-workspace"


def upgrade_command(which: Callable[[str], str | None] = shutil.which) -> tuple[str, list[str]]:
    """Return the preferred package-manager invocation without executing it."""
    if which("uv"):
        return "uv tool", ["uv", "tool", "upgrade", PACKAGE_NAME]
    if which("pipx"):
        return "pipx", ["pipx", "upgrade", PACKAGE_NAME]
    return "pip", [sys.executable, "-m", "pip", "install", "--user", "--upgrade", PACKAGE_NAME]


def render_command(command: Sequence[str]) -> str:
    """Render a command for terminal output without shell evaluation."""
    return " ".join(command)
