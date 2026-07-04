"""Workspace and actor domain models (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from server.models._row import row_required_text, row_text

ActorKind = Literal["human", "agent", "service"]


class Workspace(BaseModel):
    """Registered workspace root."""

    model_config = ConfigDict(frozen=True)

    workspace_id: str
    root_path: str
    name: str
    created_at: str

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "workspace_id",
        "root_path",
        "name",
        "created_at",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Workspace:
        return cls(
            workspace_id=row_required_text(row, "workspace_id"),
            root_path=row_required_text(row, "root_path"),
            name=row_required_text(row, "name"),
            created_at=row_required_text(row, "created_at"),
        )

    def to_row(self) -> tuple[str, str, str, str]:
        return (self.workspace_id, self.root_path, self.name, self.created_at)


class Actor(BaseModel):
    """Human, agent, or service identity."""

    model_config = ConfigDict(frozen=True)

    actor_id: str
    kind: ActorKind
    display_name: str
    identity_hint: str | None = None

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "actor_id",
        "kind",
        "display_name",
        "identity_hint",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Actor:
        return cls(
            actor_id=row_required_text(row, "actor_id"),
            kind=row_required_text(row, "kind"),  # type: ignore[arg-type]
            display_name=row_required_text(row, "display_name"),
            identity_hint=row_text(row, "identity_hint"),
        )

    def to_row(self) -> tuple[str, str, str, str | None]:
        return (self.actor_id, self.kind, self.display_name, self.identity_hint)
