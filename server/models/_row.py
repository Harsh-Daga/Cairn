"""Shared sqlite3.Row helpers for domain models."""

from __future__ import annotations

import json
import sqlite3
from typing import TypeVar

T = TypeVar("T")


def row_text(row: sqlite3.Row, key: str) -> str | None:
    value = row[key]
    return None if value is None else str(value)


def row_required_text(row: sqlite3.Row, key: str) -> str:
    return str(row[key])


def row_int(row: sqlite3.Row, key: str, *, default: int | None = None) -> int | None:
    value = row[key]
    if value is None:
        return default
    return int(value)


def row_float(row: sqlite3.Row, key: str) -> float | None:
    value = row[key]
    if value is None:
        return None
    return float(value)


def row_bool_int(row: sqlite3.Row, key: str, *, default: bool = False) -> bool:
    value = row[key]
    if value is None:
        return default
    return bool(int(value))


def parse_json(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(str(value))


def parse_json_list(value: object) -> list[object]:
    parsed = parse_json(value)
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        msg = f"expected JSON list, got {type(parsed).__name__}"
        raise TypeError(msg)
    return parsed


def parse_json_dict(value: object) -> dict[str, object]:
    parsed = parse_json(value)
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        msg = f"expected JSON object, got {type(parsed).__name__}"
        raise TypeError(msg)
    return {str(k): v for k, v in parsed.items()}


def parse_str_list(value: object) -> list[str]:
    return [str(item) for item in parse_json_list(value)]


def parse_float_list(value: object) -> list[float]:
    result: list[float] = []
    for item in parse_json_list(value):
        if isinstance(item, (int, float, str)):
            result.append(float(item))
        else:
            msg = f"expected numeric JSON value, got {type(item).__name__}"
            raise TypeError(msg)
    return result


def dump_json(value: object | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), sort_keys=True)
