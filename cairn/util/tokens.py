"""Shared token estimation heuristic (R4)."""

from __future__ import annotations

import math

from cairn.model.messages import CompletionRequest, Message, TextBlock


def estimate_tokens_from_text(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def estimate_tokens_from_messages(messages: tuple[Message, ...]) -> int:
    parts: list[str] = []
    for message in messages:
        for block in message.content:
            if isinstance(block, TextBlock):
                parts.append(block.text)
    return estimate_tokens_from_text("".join(parts))


def estimate_tokens_from_request(request: CompletionRequest) -> int:
    return estimate_tokens_from_messages(request.messages)
