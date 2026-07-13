"""Repeated failing commands."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight


def rule_failing_command(ctx: dict[str, Any]) -> Insight | None:
    commands = ctx.get("failing_commands") or []
    if not isinstance(commands, list):
        return None
    worst = next((c for c in commands if int(c.get("failures", 0)) >= 3), None)
    if worst is None:
        return None
    name = str(worst.get("name", "command"))
    failures = int(worst.get("failures", 0))
    return Insight(
        id="failing-command",
        severity="error",
        title=f"Command failing repeatedly: {name}",
        body=(
            f"`{name}` failed {failures} times in the window. "
            "Fix the underlying command or guard retries in agent rules."
        ),
        evidence={"command": name, "failures": failures},
        savings_estimate=None,
        action="cairn optimize",
    )
