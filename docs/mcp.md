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
