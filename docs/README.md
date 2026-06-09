# Cairn documentation

Cairn is a **local-first inference workspace** for AI agents and LLM workflows. It records
what your agents and models actually did — prompts, tool calls, artifacts, outputs — and
turns that into offline HTML reports with execution graphs.

## Start here

| I want to… | Read |
|------------|------|
| Install and run my first report in 5 minutes | [Getting started](getting-started.md) |
| Test every feature end-to-end | [E2E testing guide](guides/e2e-testing.md) |
| Understand projects, sessions, caching, bundles | [Concepts](concepts.md) |
| Run LLM pipelines over my repo | [Provider workflows](guides/provider-workflows.md) |
| Ingest Claude Code / Cursor / Codex sessions | [Agent capture](guides/agent-capture.md) |
| Share snapshots and sync ledgers | [Collaboration](guides/collaboration.md) |

## Reference

| Topic | Document |
|-------|----------|
| Every CLI command with examples | [CLI reference](reference/cli.md) |
| `cairn.toml`, providers, environment | [Configuration](reference/configuration.md) |
| Python API | [Python SDK](reference/sdk.md) |
| HTTP routes and curl examples | [HTTP API](reference/api.md) |
| Credentials, scrubbing, encryption | [Security](security.md) |

## How Cairn fits together

```
  Your repo                         Cairn                              Output
  ─────────                         ─────                              ──────
  markdown, code          ──►   ingest / build          ──►   .cairn/ledger.db
  agent transcripts              workflows                       content-addressed store
  cairn.toml                     providers                       HTML bundle + graphs
```

Three ways in, one report shape out:

1. **Capture** — `cairn ingest` reads agent transcripts (Claude Code, Cursor, Codex, …)
2. **Pipeline** — `cairn build` runs versioned LLM workflows over your corpus
3. **Live** — `cairn live serve` streams session updates to a browser

All paths write to the same ledger and render through the same bundle format.

## For contributors

- [Contributing](../CONTRIBUTING.md) — setup, tests, PR guidelines
- [Technical charter](spec/charter.md) — full product and implementation specification
- [Publishing](publishing.md) — PyPI release workflow (maintainers)

## Install

```bash
pip install cairn-workspace          # PyPI
pipx install cairn-workspace         # isolated CLI
uv tool install cairn-workspace
```

See [pypi.org/project/cairn-workspace](https://pypi.org/project/cairn-workspace/) or
[Getting started — Install](getting-started.md#install).

## Quick commands

```bash
# Provider pipeline (offline, no API keys)
cairn init demo && cd demo
cairn build --yes --provider-mode recorded
cairn render -o outputs/bundle --zip

# Agent capture (no cairn.toml required)
cairn ingest --source claude-code
cairn render --session <session_id> -o outputs/capture-bundle
```
