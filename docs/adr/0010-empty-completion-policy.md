# ADR 0010: Empty and truncated completions are never cached

**Status:** Accepted  
**Date:** 2026-06-07  
**Charter:** R2, R17, Phase 2.1

## Context

Reasoning models (e.g. Ollama Cloud `kimi-k2.6:cloud`) may return `finish_reason: "length"`
with empty `content` when `max_tokens` is exhausted by internal reasoning. Binding that empty
string to the Action Cache is silent corruption: subsequent builds hit the cache and reproduce
the failure until `--refresh`.

## Decision

1. Provider adapters surface `finish_reason` / `stop_reason` on `CompletionResult`.
2. `ensure_usable_completion()` raises `EmptyCompletionError` when text is empty/whitespace, or
   when truncation indicators (`length`, `max_tokens`) accompany empty text.
3. The executor never calls `cache.bind` for failed completions; the run is recorded `failed`.
4. `cairn doctor` warns when `max_tokens` is below 1024 for capability-registry models marked
   `reasoning: true`.

## Consequences

- Live builds fail loudly instead of caching poison.
- Reasoning models need adequate `max_tokens` headroom.
- Recorded fixtures with empty text + `finish_reason: length` also raise on replay.
