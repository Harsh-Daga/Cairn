# ADR 0007: System prompt is part of the action key

**Status:** Accepted  
**Date:** 2026-06-07  
**Charter:** §9 (cache-key algorithm), R1, R17 #1–#3

## Context

The Phase 1 executor sent a hardcoded system message (`"Follow the instructions precisely."`)
to providers, but the action key did not include any digest of that text. Once
`[defaults].system` or per-step `system` becomes configurable, identical keys could
return stale outputs produced under a different system prompt — silent incorrect cache hits.

No released caches or fixtures existed at acceptance time, so `cairn_key_version` stays
at `1`; only the payload shape gains a field.

## Decision

1. **Resolved system prompt** precedence (high → low): step `system` → `[defaults].system`
   → built-in `DEFAULT_SYSTEM_PROMPT` (`"Follow the instructions precisely."`).
2. **Action key payload** includes `system_hash = sha256(utf-8 bytes of resolved system)`.
3. **Provider calls** use the same resolved system string (not a separate hardcoded value).
4. **Charter §9 / R1 illustrative field list** is extended to include `system_hash` for
   chat steps; `prompt_hash` remains the Jinja template body only (ADR 0005).

## Consequences

- Changing system text invalidates every node that uses it (expected).
- Unchanged default keeps keys stable for projects that never set `system`.
- Golden-hash vectors must be re-pinned once before the first commit.
