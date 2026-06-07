"""Coalesce identical in-flight provider requests by action key (R5, R12)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class RequestCoalescer(Generic[T]):
    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Task[T]] = {}

    async def run(self, key: str, factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
        existing = self._inflight.get(key)
        if existing is not None:
            return await existing
        task: asyncio.Task[T] = asyncio.create_task(factory())
        self._inflight[key] = task
        try:
            return await task
        finally:
            self._inflight.pop(key, None)
