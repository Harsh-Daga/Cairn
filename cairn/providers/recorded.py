"""RecordedProvider — record→fixture, replay for CI (R5, §15)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cairn.model.messages import CompletionRequest, CompletionResult, TextBlock, TokenUsage
from cairn.providers.completion import ensure_usable_completion
from cairn.util.canonical import hash_obj
from cairn.util.tokens import estimate_tokens_from_request


def _request_key(request: CompletionRequest) -> str:
    payload: dict[str, Any] = {
        "model": request.model,
        "provider": request.provider,
        "params": request.params,
        "messages": [
            {
                "role": m.role,
                "content": "".join(b.text for b in m.content if isinstance(b, TextBlock)),
            }
            for m in request.messages
        ],
    }
    return hash_obj(payload)


def _deterministic_text(key: str) -> str:
    """Stable mock output from sha256 — never Python's builtin hash()."""
    return f"[recorded:{key[:16]}] deterministic completion"


class RecordedProvider:
    """Replay fixtures keyed by sha256; record mode writes new fixtures."""

    name = "recorded"

    def __init__(self, fixtures_dir: Path, *, record: bool = False) -> None:
        self.fixtures_dir = fixtures_dir
        self.record = record
        self.fixtures_dir.mkdir(parents=True, exist_ok=True)
        self.tokens_spent = 0

    def estimate_tokens(self, request: CompletionRequest) -> int:
        return estimate_tokens_from_request(request)

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        key = _request_key(request)
        path = self.fixtures_dir / f"{key}.json"
        if path.is_file() and not self.record:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.tokens_spent += 0
            result = CompletionResult(
                text=str(data["text"]),
                usage=TokenUsage(
                    input_tokens=int(data.get("input_tokens", 0)),
                    output_tokens=int(data.get("output_tokens", 0)),
                ),
                raw=data.get("raw", {}),
                finish_reason=data.get("finish_reason"),
            )
            return ensure_usable_completion(result)
        text = _deterministic_text(key)
        result = CompletionResult(
            text=text,
            usage=TokenUsage(input_tokens=42, output_tokens=17),
            raw={"fixture_key": key},
        )
        if self.record or not path.is_file():
            path.write_text(
                json.dumps(
                    {
                        "text": result.text,
                        "input_tokens": result.usage.input_tokens,
                        "output_tokens": result.usage.output_tokens,
                        "raw": result.raw,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        self.tokens_spent += result.usage.input_tokens + result.usage.output_tokens
        return ensure_usable_completion(result)
