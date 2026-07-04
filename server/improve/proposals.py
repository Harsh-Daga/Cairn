"""Deterministic proposal generator from insight evidence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from server.store.repos.insights import InsightRepo


@dataclass(frozen=True)
class Proposal:
    target_file: str
    block_key: str
    kind: str
    content: str
    evidence_id: str
    rationale: str


def generate_proposals(conn: sqlite3.Connection, *, limit: int = 10) -> list[Proposal]:
    """Map open insights to file-guide proposals."""
    rows = InsightRepo.list_by_state(conn, "new", limit=limit)
    proposals: list[Proposal] = []
    for row in rows:
        insight = row.insight
        if insight.detector == "identical-tool-calls":
            proposals.append(
                Proposal(
                    target_file="AGENTS.md",
                    block_key="avoid-duplicate-reads",
                    kind="rule",
                    content=(
                        "Before calling read/search, check if the result is already in context."
                    ),
                    evidence_id=insight.evidence_id,
                    rationale=insight.body,
                )
            )
        elif insight.detector == "context-window-pressure":
            proposals.append(
                Proposal(
                    target_file="AGENTS.md",
                    block_key="context-pressure",
                    kind="known_issue",
                    content="Split long tasks; clear consumed tool results before continuing.",
                    evidence_id=insight.evidence_id,
                    rationale=insight.body,
                )
            )
    return proposals
