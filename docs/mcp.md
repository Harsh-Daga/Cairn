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
