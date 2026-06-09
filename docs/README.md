# Cairn documentation

Welcome to Cairn — a local-first inference workspace for AI agents and LLM workflows.

## Start here

| If you want to… | Read |
|-----------------|------|
| Install and run your first workflow | [Getting started](getting-started.md) |
| Understand projects, sessions, and reports | [Concepts](concepts.md) |
| Look up a command | [CLI reference](cli.md) |
| Automate from Python | [Python SDK](sdk.md) |
| Integrate over HTTP | [HTTP API](api.md) |
| Handle secrets and sharing safely | [Security](security.md) |
| Contribute code | [Contributing](../CONTRIBUTING.md) |

## How Cairn fits together

```
  Your repo                    Cairn                         Output
  ─────────                    ─────                         ──────
  markdown, code    ──►   ingest / build    ──►   .cairn/ledger.db
  agent transcripts        workflows              content-addressed store
  cairn.toml                 providers              HTML bundle + graphs
```

Three ways in, one report out:

1. **Capture** — `cairn ingest` reads agent transcripts (Claude Code, Cursor, Codex, …)
2. **Pipeline** — `cairn build` runs versioned LLM workflows over your corpus
3. **Workspace** — `cairn live serve` streams updates to a browser

All paths write to the same ledger and render through the same bundle format.

## For contributors

- [Architecture Decision Records](adr/) — design rationale
- [Technical charter](spec/charter.md) — full product and implementation specification
