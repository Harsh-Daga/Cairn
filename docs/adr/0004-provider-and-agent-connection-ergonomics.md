# ADR 0004: Adopt Lattice's provider & agent *connection ergonomics* (only)

**Status:** Accepted
**Date:** 2026-06-08
**Charter:** §4 (principles), §10 (`cairn doctor`), R5 (provider adapter), R3 (config/secrets),
R10 (CLI-agent backend), R18 (provider & agent connection layer)
**Depends on:** [ADR 0001](0001-independence-from-lattice-and-stratum.md),
[ADR 0002](0002-exact-action-cache-only.md),
[ADR 0003](0003-prior-art-implementation-patterns.md)

## Context

A full read of the retired **Lattice** codebase (`src/lattice/providers/*`,
`src/lattice/integrations/*`, `src/lattice/cli/*`) surfaced four ergonomics patterns that make
connecting to providers and CLI agents notably easier, and that fit Cairn's charter **without**
importing Lattice or adopting its transport/proxy model. ADR 0001–0003 already rejected Lattice's
*architecture* (proxy, semantic cache, agent-config patching). This ADR records the narrow set of
*connection-convenience* patterns Cairn reimplements natively, and reaffirms the boundaries.

## Decision

Cairn reimplements, in its own codebase, the following (specified in charter **R18**):

1. **Provider capability registry** (`providers/capabilities.py`) — a pure, frozen data table:
   `provider → {default_base_url, supported_models, max_context/output_tokens, feature flags,
   cache_mode (advisory), rate-limit header names}`. Used for zero-config base-URL resolution,
   `validate`/`doctor` warnings, and header-based rate-limit pacing.

2. **Credential resolver** (`providers/credentials.py`) — precedence: runtime override → user
   config `~/.config/cairn/config.toml [providers.<name>]` → **standard env-var names**
   (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_CLOUD_API_KEY`, …) → registry default base URL.
   Makes the common case **zero-config**.

3. **Per-provider retry policy tables** (`providers/adapters/retry_policies.py`) — the R5 retry
   classification as data (`RetryRule(matches, max_attempts, backoff, respect_header)`), with
   `from_header` / `exponential` / `decorrelated_jitter` backoffs; built-in `openai` and
   `anthropic` (incl. **529**) policies + a default.

4. **`cairn doctor` + CLI-agent profile registry** (`agents/profiles.py`, Phase 4) — a no-token
   preflight, and a named registry of known CLI agents (`claude-code`, `codex`, `cursor`,
   `opencode`, `copilot`, `generic`) so `backend = "claude-code"` works; `cli:<raw>` remains the
   escape hatch.

## Hard boundaries (reaffirm ADR 0001/0002)

- **R18 never influences action keys, stored outputs, or ledger records.** It is connection
  convenience + preflight only. The capability registry's `cache_mode` is an *advisory transport
  hint*; provider-side prompt caching (if used) is transparent to the action cache.
- **No proxy/gateway server, ever** (§4 #1 zero-infra).
- **Agent profiles are invocation-only.** Cairn subprocesses an agent for one node's duration and
  captures output. It does **not** patch the agent's config, install a proxy, or run
  `init`/`lace`-style durable routing. No durable mutation of anything the user owns.
- **Secrets** still obey R3/R16: env/config only, never committed, never logged, never in keys.

## Explicitly NOT adopted

Proxy/gateway; durable agent-config patching, `lace`, mutation store, tunnel; semantic/approximate
cache (ADR 0002); compression-transform pipeline; attribution scorer; Redis/shared backends.

## Consequences

**Positive:** dramatically easier onboarding (set a standard env var → it works); smarter
preflight (`doctor`) that fails before spend; cleaner provider code (data tables vs inline glue);
the Phase-0 spike's ad-hoc Ollama endpoint logic folds into the registry.

**Negative:** a built-in provider/model table needs occasional refreshing (same maintenance as the
price table, R4) — acceptable, and overridable by users.

## Verification

- Capability registry + resolver + retry tables are pure and unit-tested (golden tests for
  resolution precedence and endpoint normalization).
- `cairn doctor` has tests for: missing key, unknown model warning, unreachable MCP server,
  missing CLI-agent binary.
- A property test asserts that **changing provider connection config (base_url, credentials,
  capability entries) does NOT change any action key** — the R18 boundary, enforced in CI.