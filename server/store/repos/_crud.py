"""Shared SQL helpers for typed repositories."""

from __future__ import annotations

import sqlite3
from typing import ClassVar, Protocol, Self, TypeVar

T = TypeVar("T", bound="RowBacked")


class RowBacked(Protocol):
    """Protocol for Pydantic models backed by sqlite3 rows."""

    INSERT_FIELDS: ClassVar[tuple[str, ...]]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Self: ...

    def to_row(self) -> tuple[object, ...]: ...


def _placeholders(count: int) -> str:
    return ", ".join("?" * count)


def insert(conn: sqlite3.Connection, table: str, model: RowBacked) -> None:
    fields = model.INSERT_FIELDS
    sql = f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({_placeholders(len(fields))})"
    conn.execute(sql, model.to_row())


def upsert(
    conn: sqlite3.Connection,
    table: str,
    model: RowBacked,
    pk_fields: tuple[str, ...],
) -> None:
    fields = model.INSERT_FIELDS
    updates = [field for field in fields if field not in pk_fields]
    conflict = ", ".join(pk_fields)
    set_clause = ", ".join(f"{field} = excluded.{field}" for field in updates)
    sql = (
        f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({_placeholders(len(fields))}) "
        f"ON CONFLICT({conflict}) DO UPDATE SET {set_clause}"
    )
    conn.execute(sql, model.to_row())


def update(
    conn: sqlite3.Connection,
    table: str,
    model: RowBacked,
    pk_fields: tuple[str, ...],
) -> bool:
    row = model.to_row()
    field_index = {name: index for index, name in enumerate(model.INSERT_FIELDS)}
    set_fields = [field for field in model.INSERT_FIELDS if field not in pk_fields]
    if not set_fields:
        return False
    values = [row[field_index[field]] for field in set_fields]
    pk_values = [row[field_index[field]] for field in pk_fields]
    set_clause = ", ".join(f"{field} = ?" for field in set_fields)
    where = " AND ".join(f"{field} = ?" for field in pk_fields)
    cur = conn.execute(
        f"UPDATE {table} SET {set_clause} WHERE {where}",
        (*values, *pk_values),
    )
    return cur.rowcount > 0


def fetch_one(
    conn: sqlite3.Connection,
    table: str,
    where: str,
    params: tuple[object, ...],
    model_cls: type[T],
) -> T | None:
    row = conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchone()
    if row is None:
        return None
    return model_cls.from_row(row)


def fetch_all(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[object, ...],
    model_cls: type[T],
) -> list[T]:
    rows = conn.execute(sql, params).fetchall()
    return [model_cls.from_row(row) for row in rows]


def delete_where(
    conn: sqlite3.Connection,
    table: str,
    where: str,
    params: tuple[object, ...],
) -> bool:
    cur = conn.execute(f"DELETE FROM {table} WHERE {where}", params)
    return cur.rowcount > 0
