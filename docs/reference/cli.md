# CLI reference

All commands live in `cairn/cli/main.py`. Run `cairn --help` or `cairn help <cmd>` for flags.

## Golden path

| Command | Description |
|---------|-------------|
| `cairn [project]` | Detect → sync → summary → dashboard (background) |
| `cairn --foreground` / `-f` | Same, server stays in foreground |
| `cairn stop` | Stop background dashboard |

## Data

| Command | Description |
|---------|-------------|
| `cairn sync [project]` | Ingest agent logs (`--source`, `--since`, `--verify`) |
| `cairn share [id]` | Export scrubbed HTML bundle (`-o`, `--zip`, `--receipt`) |
| `cairn config get [section.key]` | Read `~/.config/cairn/config.toml` (`config get diagnose` shows defaults) |
| `cairn config set section.key value` | Write config (e.g. `config set diagnose.cascade_k 4`) |

`cairn sync --verify` re-parses on-disk transcripts and reports drift vs the ledger (event counts, token totals) without writing.

## Pillars

| Command | Description |
|---------|-------------|
| `cairn show [id]` | Session timeline + graph (`--json`) |
| `cairn profile [id]` | Context regions + findings |
| `cairn behavior` | Fingerprints + drift |
| `cairn outcomes` | Quality scores + funnel |
| `cairn mcp install` | Print MCP client config |
| `cairn diagnose [id]` | Session autopsy in the terminal (includes rewind suggestion when git allows) |
| `cairn expect <prompt>` | Difficulty-aware budget forecast |

## Optimize

| Command | Description |
|---------|-------------|
| `cairn optimize` | List proposals |
| `cairn optimize --apply` | Apply selected proposals |
| `cairn optimize --revert ID` | Revert a managed block |

## CI / gates

| Command | Description |
|---------|-------------|
| `cairn check [project]` | Preflight + optional gates |
| `cairn check --budget-usd N` | Fail if total spend exceeds N |
| `cairn check --budget-tokens N` | Fail if total tokens exceed N |
| `cairn check --max-waste-ratio R` | Fail if waste ratio exceeds R |
| `cairn check --min-quality N` | Fail if 7d mean `quality_score` < N |
| `cairn check --format github` | Emit `::error` / `::warning` workflow commands for failing gates |
| `cairn check --json` | Machine-readable output |

## Dashboard

| Command | Description |
|---------|-------------|
| `cairn dash [project]` | Start dashboard (`--port`, `--no-open`) |

## Advanced

| Command | Description |
|---------|-------------|
| `cairn advanced migrate` | Drop ledger + re-ingest (schema recovery) |
| `cairn advanced post-session` | Hidden: re-ingest one session + diagnostics (Stop hook worker) |
| `cairn advanced tokenizer-check` | Report heuristic tokenizer error % vs measured fixtures |
| `cairn guard install` | Install PreToolUse + Stop hooks (`--agent claude|codex|both`, `--write`) |
| `cairn hook pretooluse` | PreToolUse hook handler (fail-open) |
| `cairn hook stop` | Stop hook handler (enqueue post-session) |

## Legacy aliases

Old v2 commands redirect: `cairn ingest` → `sync`, `cairn render` → `share`, `cairn doctor` → `check`, etc.
