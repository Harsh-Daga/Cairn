"""Shared Sessions/Search filter response contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class QueryFilterToken(BaseModel):
    raw: str
    field: Literal[
        "agent",
        "source",
        "status",
        "cost",
        "outcome",
        "file",
        "tool",
        "after",
        "claim",
        "verification",
        "corrected",
        "risk",
    ]
    value: str
    comparison: Literal["eq", "gt", "gte", "lt", "lte"]
    available: bool


class QueryFilterError(BaseModel):
    token: str
    message: str
