# MCP setup

Expose read-only Cairn ledger context to a coding agent over stdio.

```bash
# Print install payload without writing client config
cairn mcp install --print

# Write config for a known client
cairn mcp install --client cursor
cairn mcp install --client claude-code
cairn mcp install --client codex

# Start the MCP server (stdio)
cairn mcp
```

Agent bootstrap prompt (paste into a new chat):

```bash
cairn setup-prompt
```

Also see [AGENT_SETUP.md](../../AGENT_SETUP.md) and [docs/mcp.md](../../docs/mcp.md).

MCP opens the ledger with SQLite `mode=ro` and does not mutate the database.
