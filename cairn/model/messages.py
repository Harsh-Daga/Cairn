"""Normalized message model for providers (R5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class TextBlock:
    text: str


@dataclass(frozen=True)
class Message:
    role: Role
    content: tuple[TextBlock, ...]


@dataclass(frozen=True)
class CompletionRequest:
    model: str
    messages: tuple[Message, ...]
    params: dict[str, Any]
    provider: str


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class CompletionResult:
    text: str
    usage: TokenUsage
    raw: dict[str, Any]
