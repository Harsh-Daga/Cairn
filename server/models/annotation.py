"""Annotation domain model (Phase 1)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from server.models._row import row_required_text, row_text


class Annotation(BaseModel):
    """Human note attached to a trace, span, or insight."""

    model_config = ConfigDict(frozen=True)

    annotation_id: str
    subject_type: str
    subject_id: str
    body: str
    author: str | None = None
    created_at: str

    INSERT_FIELDS: ClassVar[tuple[str, ...]] = (
        "annotation_id",
        "subject_type",
        "subject_id",
        "body",
        "author",
        "created_at",
    )

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Annotation:
        return cls(
            annotation_id=row_required_text(row, "annotation_id"),
            subject_type=row_required_text(row, "subject_type"),
            subject_id=row_required_text(row, "subject_id"),
            body=row_required_text(row, "body"),
            author=row_text(row, "author"),
            created_at=row_required_text(row, "created_at"),
        )

    def to_row(self) -> tuple[str, str, str, str, str | None, str]:
        return (
            self.annotation_id,
            self.subject_type,
            self.subject_id,
            self.body,
            self.author,
            self.created_at,
        )
