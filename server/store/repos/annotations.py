"""Annotation repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.annotation import Annotation
from server.store.pagination import bounded_page
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "annotations"
_PK = ("annotation_id",)


class AnnotationRepo:
    """CRUD for the annotations table."""

    @staticmethod
    def create(conn: sqlite3.Connection, annotation: Annotation) -> None:
        insert(conn, _TABLE, annotation)

    @staticmethod
    def upsert(conn: sqlite3.Connection, annotation: Annotation) -> None:
        upsert(conn, _TABLE, annotation, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, annotation_id: str) -> Annotation | None:
        return fetch_one(conn, _TABLE, "annotation_id = ?", (annotation_id,), Annotation)

    @staticmethod
    def list_by_subject(
        conn: sqlite3.Connection,
        subject_type: str,
        subject_id: str,
    ) -> list[Annotation]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} WHERE subject_type = ? AND subject_id = ? "
            "ORDER BY created_at ASC",
            (subject_type, subject_id),
            Annotation,
        )

    @staticmethod
    def list_all(
        conn: sqlite3.Connection, *, limit: int = 100, offset: int = 0
    ) -> list[Annotation]:
        limit, offset = bounded_page(limit, offset)
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
            Annotation,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, annotation: Annotation) -> bool:
        return update(conn, _TABLE, annotation, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, annotation_id: str) -> bool:
        return delete_where(conn, _TABLE, "annotation_id = ?", (annotation_id,))
