"""CLI-agent profile registry for doctor and pipeline invocation (R18.4)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Literal

AgentProfileId = Literal[
    "claude-code",
    "codex",
    "cursor",
    "opencode",
    "copilot",
    "generic",
]


@dataclass(frozen=True)
class AgentProfile:
    profile_id: AgentProfileId
    label: str
    binaries: tuple[str, ...]


_PROFILES: dict[AgentProfileId, AgentProfile] = {
    "claude-code": AgentProfile("claude-code", "Claude Code", ("claude",)),
    "codex": AgentProfile("codex", "Codex", ("codex",)),
    "cursor": AgentProfile("cursor", "Cursor", ("cursor",)),
    "opencode": AgentProfile("opencode", "OpenCode", ("opencode",)),
    "copilot": AgentProfile("copilot", "GitHub Copilot CLI", ("copilot",)),
    "generic": AgentProfile("generic", "Generic CLI agent", ()),
}


def get_profile(profile_id: str) -> AgentProfile | None:
    for key, profile in _PROFILES.items():
        if key == profile_id:
            return profile
    return None


def list_profile_ids() -> tuple[AgentProfileId, ...]:
    return tuple(_PROFILES.keys())


def binary_on_path(name: str) -> bool:
    return shutil.which(name) is not None


def check_profile(profile_id: str) -> tuple[bool, str]:
    """Return (ok, message) for doctor."""
    profile = get_profile(profile_id)
    if profile is None:
        return False, f"unknown agent profile {profile_id!r}"
    if not profile.binaries:
        return True, f"agent profile {profile_id!r} has no required binary"
    missing = [b for b in profile.binaries if not binary_on_path(b)]
    if missing:
        return False, f"agent profile {profile_id!r}: missing on PATH: {', '.join(missing)}"
    return True, f"agent profile {profile_id!r}: {profile.binaries[0]} found"
