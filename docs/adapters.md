# Ingest adapters

Cairn normalizes agent logs through **adapters** in `server/ingest/adapters/`. Each adapter discovers log files for a workspace and parses them into a `ParsedSession` (events, tool calls, usage). The pipeline in `server/ingest/pipeline.py` writes traces and spans to `.cairn/cairn.db`.

## Quick start: scaffold a new adapter

```bash
cairn adapter new my_agent
```

This creates:

| Path | Purpose |
|------|---------|
| `server/ingest/adapters/my_agent_adapter.py` | Parser stub extending `FileAdapterBase` |
| `tests/fixtures/ingest/my_agent_mini.jsonl` | Minimal fixture |
| `tests/test_ingest_my_agent.py` | Smoke test |

Register the adapter via **entry point** in `pyproject.toml`:

```toml
[project.entry-points."cairn.adapters"]
my_agent = "server.ingest.adapters.my_agent_adapter:MyAgentAdapter"
```

Or add the class to `build_adapters()` in `server/ingest/registry.py`.

## Conformance harness

Every adapter must pass `tests/adapter_conformance.py`:

```bash
uv run pytest tests/adapter_conformance.py -q
```

The harness checks, for each adapter + fixture pair:

- **Determinism** — parse twice → identical `span_id`s
- **Monotonic seq** — strictly increasing, unique sequence numbers
- **Parent refs** — every `parent_span_id` resolves to a span in the trace
- **Valid kinds** — span kinds within the current schema
- **Quality record** — `DataQuality` present with `trace_id` and `cost_source`

An adapter PR is **one parser + one fixture + harness green**.

## Built-in adapters

| Adapter ID | Agent | Fixture |
|------------|-------|---------|
| `claude_code` | Claude Code | `claude_code_mini.jsonl` |
| `codex` | Codex CLI | `codex_mini.jsonl` |
| `cursor` | Cursor | `cursor_mini.jsonl` |
| `cline` | Cline | `cline_mini/tasks/.../ui_messages.json` |
| `roo` | Roo Code | same Cline-family fixture |
| `kilo` | Kilo Code | same Cline-family fixture |
| `goose` | Goose | `agent_jsonl_mini.jsonl` |
| `aider` | Aider | `agent_jsonl_mini.jsonl` |
| `gemini_cli` | Gemini CLI | `gemini_mini.jsonl` |
| `opencode` | OpenCode | `agent_jsonl_mini.jsonl` |
| `hermes` | Hermes | `hermes_mini.json` |
| `openclaw` | OpenClaw | `openclaw_mini.jsonl` |

Filter sync to one adapter:

```bash
cairn sync --source cursor
```

## OTLP push ingest

Agents that emit OpenTelemetry can POST to:

```
POST /v1/traces
```

JSON (`application/json`) and protobuf (`application/x-protobuf`) are supported. See [api.md](api.md).

## Workspace filtering

Discovery functions filter sessions to the active git workspace where possible (Claude project slug, Codex cwd, Cursor slug). Global log stores (Hermes, Gemini) use path heuristics.

## Estimation accuracy

Per-adapter fixture parse coverage and token estimation error are published in
[ACCURACY.md](../ACCURACY.md). The same `scripts/gen_accuracy.py` CI step refreshes both the
human-readable table and the packaged data used by `cairn adapter doctor`.

## Parse-health canaries

Every changed stream parse is recorded as fully parsed, degraded, or skipped. Cairn also compares
a bounded live sample with the adapter's expected top-level shape and counts unknown fields. The
workspace API and Settings show parse coverage, unknown-field counts, and last successful parse.

Coverage below 90%, or at least three unknown fields in the latest sample, produces a dashboard
banner and a failing `cairn doctor` check: “&lt;agent&gt; log format may have changed; numbers may be
incomplete.” The warning links to a prefilled adapter issue. No log content is sent anywhere;
opening the issue is an explicit user action.

For a field-level diagnosis against the newest detected stream (or an explicit bounded sample):

```bash
cairn adapter doctor claude_code
cairn adapter doctor claude_code --sample /path/to/session.jsonl
```

The report names recognized and unknown top-level fields, whether normalization succeeded,
normalized and dropped event counts, and the token method/MAPE published in `ACCURACY.md`.
Adapters without an expected-token fixture report accuracy as “not measured.”
