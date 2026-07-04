"""Ingest cursor domain model (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from server.models._row import dump_json, parse_json_dict, row_required_text


class IngestCursor(BaseModel):
    """Per-adapter incremental ingest position."""

    model_config = ConfigDict(frozen=True)

    source: str
    stream: str
    cursor: dict[str, object] = Field(default_factory=dict)
    updated_at: str

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "source",
        "stream",
        "cursor_json",
        "updated_at",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> IngestCursor:
        return cls(
            source=row_required_text(row, "source"),
            stream=row_required_text(row, "stream"),
            cursor=parse_json_dict(row["cursor_json"]),
            updated_at=row_required_text(row, "updated_at"),
        )

    def to_row(self) -> tuple[str, str, str, str]:
        return (self.source, self.stream, dump_json(self.cursor) or "{}", self.updated_at)
