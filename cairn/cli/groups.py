"""Unified CLI command groups (Phase 16)."""

from __future__ import annotations

COMMAND_GROUPS: dict[str, tuple[str, ...]] = {
    "Project": ("init", "validate", "doctor", "status", "plan"),
    "Workflows": ("context", "prompt", "workflow", "build"),
    "Capture": ("ingest", "watch", "hook", "sessions", "show", "live"),
    "Observability": ("runs", "render", "report", "graph", "artifact", "diff"),
    "Sharing": ("snapshot", "collab"),
    "API": ("api",),
}

ALL_COMMANDS: tuple[str, ...] = tuple(
    cmd for group in COMMAND_GROUPS.values() for cmd in group
)
