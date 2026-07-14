"""Repeated failing commands."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from server.improve.detectors._types import FixPayload, Insight, LiveDetection


def detect_live_failing_command(spans: list[dict[str, Any]]) -> LiveDetection | None:
    """Detect the same command/tool failing at least three times in the live tail."""
    failures: dict[str, list[int]] = defaultdict(list)
    for span in spans:
        if span.get("kind") == "tool_call" and span.get("status") == "error":
            failures[str(span.get("name") or "command")].append(int(span.get("seq") or 0))
    if not failures:
        return None
    name, seqs = max(failures.items(), key=lambda item: len(item[1]))
    if len(seqs) < 3:
        return None
    return LiveDetection(
        pattern="failing_command",
        count=len(seqs),
        first_seen_seq=min(seqs),
        advice=(
            f"You've run {name} {len(seqs)}× with failures — read the error output before "
            "retrying and change one input or configuration."
        ),
        priority=50,
    )


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
        savings_unavailable_reason=(
            "Command failures are counted, but their per-attempt token cost is unavailable."
        ),
        fix=FixPayload(
            kind="instruction",
            label="Copy failing-command rule",
            value=(
                f"Do not rerun `{name}` unchanged after it fails; read the error, change one "
                "input or configuration, then retry once."
            ),
        ),
        action="cairn optimize",
    )
