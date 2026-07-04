# Agent capture

Cairn reads agent logs already on disk — no instrumentation required.

## Sync

```bash
cairn sync                        # all detected sources
cairn sync --source cursor        # one source
cairn sync --since 7d
```

Or use the dashboard **Sync** button.

## Log locations

| Source | Canonical path |
|--------|----------------|
| Claude Code | `~/.claude/projects/<encoded-cwd>/*.jsonl` |
| Codex | `~/.codex/sessions/YYYY/MM/DD/*.jsonl` |
| Cursor | `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` (mac) |
| OpenCode | `~/.local/share/opencode/sessions/` |
| Goose | `~/.local/share/goose/sessions/` |
| Hermes | `~/.hermes/sessions/*.json` |
| Aider | `~/.aider/chat-history/` + per-project `.aider.chat.history.md` |

Cursor: `state.vscdb` is canonical for timestamps and `tokenCount`. Agent-transcript JSONL provides tool structure only. Live sessions update via vscdb watcher (2s debounce).

## Best-of-N subagents

Cursor subcomposer runs (`isBestOfNSubcomposer`) are labeled `best-of-n-subagent` with `has_cost=0` so parent composer totals are not double-counted.

## Hooks (optional live capture)

```bash
cairn sync --watch    # install Claude Code + Codex hooks in project
cairn guard install   # PreToolUse loop guard + Stop autopsy hooks
cairn guard install --agent codex --write
```

### Guard hook JSON contracts

PreToolUse hooks receive one JSON object on stdin (all fields optional). Cairn reads `session_id`, `cwd`, `tool_name`, and related fields; malformed input or missing ledger data **fail open** (exit 0, no stdout).

**Advisory (default)** — when `should_stop` fires:

```json
{"continue": true, "systemMessage": "cairn guard: <reason>. <suggestion>"}
```

**Healthy path** — print nothing, exit 0.

**Block mode** (`--mode block` and `[guard].allow_block = true` in config):

```json
{"hookSpecificOutput": {
  "hookEventName": "PreToolUse",
  "permissionDecision": "deny",
  "permissionDecisionReason": "cairn guard: <reason>. Denied to break the loop. Next step: <suggestion>"
}}
```

If block is requested but `guard.allow_block=false`, Cairn degrades to the advisory `systemMessage` with suffix `(block requested but guard.allow_block=false)`.

**Stop hook** — `cairn hook stop` reads `session_id`, `transcript_path`, `cwd`; prints nothing; exit 0; enqueues `cairn advanced post-session` in the background.

### Install targets

| Agent | Config path | Command |
|-------|-------------|---------|
| Claude Code | `<project>/.claude/settings.json` | `cairn guard install --agent claude --write` |
| Codex CLI | `<project>/.codex/hooks.json` | `cairn guard install --agent codex --write` |

Both register PreToolUse (`cairn hook pretooluse`) and Stop (`cairn hook stop`) with matcher `*`.

Codex maps `apply_patch` edits the same as other edit tools for loop detection.

## Session detail

```bash
cairn show SESSION_ID
cairn profile SESSION_ID
cairn share SESSION_ID
```

Or open from the dashboard Sessions table.

## MCP self-awareness

Cairn exposes MCP tools (see `cairn mcp`) including:

| Tool | Use |
|------|-----|
| `cairn_project_primer` | Session-start context: waste hotspots, rules, optional `task` for cost warning |
| `cairn_should_i_stop` | Mid-session loop guard — call every ~10–20 tool calls; returns `{should_stop, reason, suggestion}` |
| `cairn_diagnose_last` | Why the last session struggled |
| `cairn_expected_cost` | Difficulty-aware budget before starting |
| `cairn_known_pitfalls` | Files that historically seed cascades |

Configure agents to invoke `cairn_should_i_stop` periodically during long tool-heavy turns (same pattern as `cairn_have_i_read` dedup checks).
