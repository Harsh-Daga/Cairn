"""Provider protocol (R5)."""

from __future__ import annotations

from typing import Protocol

from cairn.model.messages import CompletionRequest, CompletionResult


class Provider(Protocol):
    name: str

    async def complete(self, request: CompletionRequest) -> CompletionResult: ...

    def estimate_tokens(self, request: CompletionRequest) -> int: ...
