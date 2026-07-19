# MCP tools

Cairn's MCP server exposes local ledger context to coding agents over stdio. Start it with
`cairn mcp` or install client configuration with `cairn mcp install`. The ledger connection is
opened with SQLite `mode=ro`; MCP context never mutates Cairn's database.

## Live loop guard

`cairn_should_i_stop` evaluates the latest trace tail with the same detector modules used by
the improvement engine:

- `retry_loops` — tool call, error, then the same tool within three later spans;
- `identical_calls` — repeated tool calls with the same recorded argument/content hash;
- `error_streak` — at least four consecutive error spans; and
- `failing_command` — the same command/tool failing at least three times.

The response always contains `should_stop`, `trace_id`, `pattern`, `count`,
`first_seen_seq`, and actionable `advice`. A clear tail returns `pattern=null` and explains
which patterns were checked. Cairn reads at most the latest 50 spans, so the call remains
bounded during long sessions.

## Before you read

`cairn_before_you_read {"path":"..."}` can avoid a repeat file read. During normal analysis,
files read at least twice are cached with their SHA-256 identity, nanosecond mtime, read count,
and a deterministic structural summary capped at 120 whitespace tokens. No LLM or network is
used to generate it.

At call time the read-only MCP process hashes the current local file. It returns
`should_read=false` and the cached summary only when both hash and mtime still match. Changed,
missing, outside-workspace, never-read, and not-yet-hot files return `should_read=true` with a
specific reason. When content was unavailable at analysis time, Cairn falls back to read-count
and last-read metadata instead of inventing a summary.

## Context budget

`cairn_context_budget` returns a read-only composition of the current or selected session's
recorded `context_regions`:

- region token/cost shares;
- largest removable or stale regions (user region is never offered);
- one conservative trim suggestion with an explicit non-mutation limitation;
- `data_as_of` and `estimate_status` (`measured` when region rows exist, `estimated` when only
  trace rollups exist, otherwise `unavailable`).

Pass `trace_id` (or `session_id`) when more than one active session makes auto-detection
ambiguous. Missing traces, empty ledgers, and sessions without region rows return structured
errors or partial payloads — Cairn does not invent composition or call a provider.

## Handoff capsule

`cairn_handoff` returns a compact offline continuation packet (`cairn.handoff.v1`) for the current
or selected session: goal, decisions, blockers, files, tools, tests, corrections, verification
debt, and recommended next checks. Every statement is tagged `fact`, `inference`, or
`recommendation`. Paths and secrets are scrubbed; the raw transcript is omitted. No provider or
network call is made.

## Evidence tools

Additional read-only tools (no mutation, no provider call; consultation markers recorded):

| Tool | Purpose |
|------|---------|
| `cairn_verification_status` | Receipt status, active debt, remaining checks |
| `cairn_policy_check` | Advisory eval of proposed path/command (`enforcement_source`) |
| `cairn_regression_context` | Local regression acceptance criteria |
| `cairn_next_evidence` | Smallest next check preview with approval class (never executes) |

Pass `trace_id` / `regression_id` when auto-detection would be ambiguous.

## Consultation visibility

Every successful or failed Cairn MCP tool invocation appends a minimal event to
`.cairn/mcp-events.jsonl`: event ID, latest trace ID, insertion sequence, tool name, and timestamp.
Arguments, paths, prompts, code, and tool results are never recorded. The MCP SQLite connection
remains `mode=ro`; a later normal `cairn sync` idempotently imports these sidecar events through
the ledger's single writer.

Imported events appear in Session detail at the matching point in the waterfall as **agent
consulted Cairn here**. Replay hides markers beyond the selected sequence. This makes an agent
catching a retry loop visible without placing synthetic rows in the adapter-owned span sequence.
