"""Target detection: write once to AGENTS.md, bridge every observed agent."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

CANONICAL = "AGENTS.md"


@dataclass
class Target:
    path: str  # relative to the project root
    role: str  # "canonical" | "bridge"
    action: str  # human-readable description of the edit
    managed: bool = True  # whether the edit lives inside a managed block


@dataclass
class TargetPlan:
    root: Path
    canonical: Target
    bridges: list[Target] = field(default_factory=list)

    def all_targets(self) -> list[Target]:
        return [self.canonical, *self.bridges]

    def describe(self) -> str:
        lines = ["Optimization targets:"]
        for t in self.all_targets():
            lines.append(f"  {t.path}  [{t.role}] — {t.action}")
        return "\n".join(lines)


def observed_sources_from_ledger(root: Path) -> set[str]:
    """Distinct ``runs.source`` values recorded in the project ledger."""
    db = root / ".cairn" / "ledger.db"
    if not db.is_file():
        return set()
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT DISTINCT source FROM runs WHERE source IS NOT NULL").fetchall()
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()
    return {str(r[0]) for r in rows}


def detect_targets(root: Path, *, observed_sources: set[str] | None = None) -> TargetPlan:
    """Build the target plan for ``root``.

    ``observed_sources`` overrides ledger inspection (used by the engine, which already
    knows which agents produced sessions).
    """
    observed = (
        observed_sources if observed_sources is not None else observed_sources_from_ledger(root)
    )
    canonical = Target(
        path=CANONICAL,
        role="canonical",
        action="maintain the agent guide in a managed block",
    )
    bridges: list[Target] = []

    if "claude-code" in observed:
        bridges.append(
            Target(
                path="CLAUDE.md",
                role="bridge",
                action="ensure an `@AGENTS.md` import line exists",
            )
        )
    if observed & {"gemini", "hermes"}:
        bridges.append(
            Target(
                path="GEMINI.md",
                role="bridge",
                action="point to AGENTS.md for project rules",
            )
        )
    if "copilot" in observed:
        bridges.append(
            Target(
                path=".github/copilot-instructions.md",
                role="bridge",
                action="point to AGENTS.md for project rules",
            )
        )
    # Legacy Cursor: only bridge an existing .cursorrules; modern Cursor reads AGENTS.md.
    if (root / ".cursorrules").is_file():
        bridges.append(
            Target(
                path=".cursorrules",
                role="bridge",
                action="point to AGENTS.md inside a managed region",
            )
        )

    return TargetPlan(root=root, canonical=canonical, bridges=bridges)
