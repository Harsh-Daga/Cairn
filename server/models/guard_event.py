"""Guard instruction-file event domain model."""

from __future__ import annotations

import sqlite3
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.models._row import dump_json, parse_str_list, row_required_text, row_text

GuardEventKind = Literal["edit", "rename", "revert", "merge", "dirty_snapshot", "unavailable"]
GuardGitState = Literal["clean", "dirty", "no_git", "merge", "rename", "unknown"]


class GuardEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    workspace_id: str
    occurred_at: str
    path_rel: str
    event_kind: GuardEventKind
    commit_sha: str | None = None
    parent_sha: str | None = None
    before_hash: str | None = None
    after_hash: str | None = None
    diff_summary: str | None = None
    git_state: GuardGitState = "unknown"
    source: str = "git"
    confound_notes: list[str] = Field(default_factory=list)
    linked_experiment_id: str | None = None
    created_at: str

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "event_id",
        "workspace_id",
        "occurred_at",
        "path_rel",
        "event_kind",
        "commit_sha",
        "parent_sha",
        "before_hash",
        "after_hash",
        "diff_summary",
        "git_state",
        "source",
        "confound_notes_json",
        "linked_experiment_id",
        "created_at",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> GuardEvent:
        notes_raw = row["confound_notes_json"]
        return cls(
            event_id=row_required_text(row, "event_id"),
            workspace_id=row_required_text(row, "workspace_id"),
            occurred_at=row_required_text(row, "occurred_at"),
            path_rel=row_required_text(row, "path_rel"),
            event_kind=row_required_text(row, "event_kind"),  # type: ignore[arg-type]
            commit_sha=row_text(row, "commit_sha"),
            parent_sha=row_text(row, "parent_sha"),
            before_hash=row_text(row, "before_hash"),
            after_hash=row_text(row, "after_hash"),
            diff_summary=row_text(row, "diff_summary"),
            git_state=row_required_text(row, "git_state"),  # type: ignore[arg-type]
            source=row_required_text(row, "source"),
            confound_notes=parse_str_list(notes_raw) if notes_raw is not None else [],
            linked_experiment_id=row_text(row, "linked_experiment_id"),
            created_at=row_required_text(row, "created_at"),
        )

    def to_row(self) -> tuple[object, ...]:
        return (
            self.event_id,
            self.workspace_id,
            self.occurred_at,
            self.path_rel,
            self.event_kind,
            self.commit_sha,
            self.parent_sha,
            self.before_hash,
            self.after_hash,
            self.diff_summary,
            self.git_state,
            self.source,
            dump_json(self.confound_notes) if self.confound_notes else None,
            self.linked_experiment_id,
            self.created_at,
        )
