# Agent capture

Ingest transcripts from coding agents and render **Cairn Capture** HTML bundles — timeline,
execution graph, and file artifacts.

Capture works in **any git repository**. No `cairn.toml` required.

## Supported sources

| Source | Flag | Transcript location |
|--------|------|---------------------|
| Claude Code | `claude-code` | `~/.claude/projects/<slug>/*.jsonl` |
| Codex | `codex` | Codex rollout files |
| Cursor | `cursor` | `agent-transcripts/**/*.jsonl` under workspace |
| Hermes | `hermes` | Hermes session JSON |
| Aider | `aider` | Aider chat logs |
| OpenHands | `openhands` | OpenHands JSONL |
| Goose | `goose` | Goose session files |
| All | `all` | Scan every supported source |

```bash
cairn ingest --source claude-code
cairn ingest --source all
cairn ingest --source claude-code --since 7d
```

Incremental ingest uses `.cairn/watch/cursors.json` to skip unchanged files:

```
claude-code: scanned 2, inserted 0, skipped 2
```

## Claude Code slug

Cairn maps your repo path to a Claude project slug (`/` → `-`):

```bash
python3 -c "from pathlib import Path; print(Path('.').resolve().as_posix().replace('/','-'))"
# e.g. /Users/you/cairn/cairn-e2e-test → -Users-you-cairn-cairn-e2e-test
```

Transcripts live at: `$HOME/.claude/projects/<slug>/`

## Simulated ingest (fixture, no agent)

For testing without running Claude Code:

```bash
cd ~/cairn-e2e-test
CLAUDE_SLUG=$(python3 -c "from pathlib import Path; print(Path('.').resolve().as_posix().replace('/','-'))")
mkdir -p "$HOME/.claude/projects/$CLAUDE_SLUG"

cp tests/fixtures/ingest/claude_code_mini.jsonl \
   "$HOME/.claude/projects/$CLAUDE_SLUG/sess-e2e-001.jsonl"

cairn ingest --source claude-code --json
```

Expected ingest output:

```json
[{"source": "claude-code", "scanned": 1, "inserted": 1, "skipped": 0}]
```

## Inspect sessions

```bash
cairn sessions list
cairn show sess-redacted-001
```

Example `show` output:

```
Session: sess-redacted-001
Source:  claude-code
Status:  completed
Events:  4
Started: 2026-06-01T10:00:00Z
Ended:   2026-06-01T10:00:05Z
Tokens:  10 in / 5 out
```

## Graphs and reports

```bash
cairn graph sess-redacted-001 --kind execution
cairn graph sess-redacted-001 --kind artifact
cairn report --session sess-redacted-001 --json | head -40
cairn artifact list sess-redacted-001
cairn sessions replay sess-redacted-001 -o outputs/replay-bundle
```

Execution graph example (4 events):

```json
{
  "nodes": [
    {"id": "e1", "type": "user_prompt", "label": "Fix the parser test"},
    {"id": "e2", "type": "assistant_message"},
    {"id": "e3", "type": "tool_call", "label": "Edit"},
    {"id": "e4", "type": "tool_result"}
  ],
  "edges": [
    {"from": "e1", "to": "e2", "kind": "temporal"},
    {"from": "e3", "to": "e4", "kind": "causal"}
  ]
}
```

Artifact graph may be empty for minimal fixtures — that is expected.

## Render capture bundle

```bash
cairn render --session sess-redacted-001 -o outputs/capture-bundle
open outputs/capture-bundle/index.html
```

The **Cairn Capture** UI has three tabs:

| Tab | Content |
|-----|---------|
| **Timeline** | Turn cards: user prompt, assistant reply, tool calls |
| **Graph** | Interactive DAG of events |
| **Files** | File artifacts (empty if fixture has no snapshots) |

## Session diff

```bash
# Second fixture with different session id
sed 's/sess-redacted-001/sess-redacted-002/g' \
  tests/fixtures/ingest/claude_code_mini.jsonl \
  > "$HOME/.claude/projects/$CLAUDE_SLUG/sess-e2e-002.jsonl"

cairn ingest --source claude-code
cairn diff sess-redacted-001 sess-redacted-002
```

```
Session A: sess-redacted-001 (4 events, completed)
Session B: sess-redacted-002 (4 events, completed)
  shared tools: Edit
```

## Hooks and live capture

```bash
cairn live install --source all
cairn live status
cairn watch status
```

After a real Claude Code session in the same repo:

```bash
cairn ingest --source claude-code
cairn live serve --session <SESSION_ID> --port 8787
# http://127.0.0.1:8787/session/<SESSION_ID>
```

Cleanup:

```bash
cairn live uninstall
cairn watch uninstall
```

## Related

- [CLI reference](../reference/cli.md) — ingest flags
- [HTTP API](../reference/api.md) — list sessions, SSE events
- [E2E testing](e2e-testing.md) — full checklist
