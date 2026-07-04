<p align="center">
  <strong>Cairn watches what your AI agents actually do, profiles where every token goes,<br>
  learns each agent's behavioral fingerprint, ties behavior to real outcomes,<br>
  and rewrites your instruction files to fix the waste — then proves the fix worked.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python"></a>
  <a href="https://pypi.org/project/cairn-workspace/"><img src="https://img.shields.io/badge/version-0.0.1-blue.svg" alt="v0.0.1"></a>
</p>

---

## 30-second quickstart

```bash
pip install cairn-workspace
# or: uv tool install cairn-workspace

cd your-repo
cairn
```

Cairn detects installed agents, syncs their logs, computes metrics, starts a local dashboard at `http://127.0.0.1:8787`, and opens your browser. The server backgrounds automatically — use `cairn stop` to quit, or `cairn --foreground` to keep it in the terminal.

No account. No cloud. No config file required to start.

---

## The five pillars

**Context profiling** — Decompose each turn into regions (system, tool schema, tool results, retrieved files, user, history). Surface re-billing waste and concrete fixes: cache, clear stale results, drop unused tools.

**Behavioral fingerprinting** — Compress each session into a behavioral vector. Detect drift with AMDM (Mahalanobis + per-axis EWMA). See when your agent's behavior changed and which axes moved.

**Outcome-anchored quality** — After sessions, capture git and test signals. Score process quality (not just pass/fail). Flag brittle "lucky pass" sessions.

**Measured self-improvement** — Propose instruction edits to `CLAUDE.md`, `AGENTS.md`, `.cursor/rules`. Apply with human approval. Measure before/after on a holdout window. Select rules via Thompson sampling.

**Agent self-awareness (MCP)** — Ship an MCP server so agents query Cairn mid-session: "have I read this file?", "what's my recurring waste?", "fetch the project primer". Auto-installs on first run (disable in Settings → MCP).

---

## Supported agents

| Agent | Log source |
|-------|------------|
| Claude Code | `~/.claude/projects/…/*.jsonl` |
| Codex CLI | `~/.codex/sessions/…/*.jsonl` |
| Cursor | `state.vscdb` (canonical) + agent transcripts |
| OpenCode | `~/.local/share/opencode/sessions/` |
| Goose | `~/.local/share/goose/sessions/` |
| Hermes | `~/.hermes/sessions/*.json` |
| Aider | `~/.aider/chat-history/` |
| Gemini CLI | `~/.gemini/tmp/**`, `~/.config/gemini/` |
| Cline / Roo / Kilo | VS Code `globalStorage/…/tasks/*/ui_messages.json` |
| OpenClaw | `~/.openclaw/**` |

---

## CLI quick reference

| Command | What it does |
|---------|--------------|
| `cairn` | Golden path: detect → sync → dashboard (background) |
| `cairn --foreground` / `-f` | Same, but server stays in foreground |
| `cairn stop` | Stop background dashboard |
| `cairn sync` | Re-ingest agent logs |
| `cairn show ID` | Session timeline + graph |
| `cairn profile ID` | Context regions + waste findings |
| `cairn behavior` | Fingerprint + drift |
| `cairn outcomes` | Quality scores + cost-per-success |
| `cairn optimize` | Evidence → instruction proposals |
| `cairn check` | Preflight + CI gates |
| `cairn check --min-quality 70` | Fail if 7d mean quality score drops below 70 |
| `cairn mcp install` | Print MCP config block |
| `cairn config get/set` | Edit `~/.config/cairn/config.toml` |
| `cairn advanced migrate` | Drop ledger + re-ingest (schema recovery) |

Every dashboard action (sync, export, MCP install, check, optimize apply) is also a button in the UI.

---

## Architecture (ASCII)

```
 agent logs ──► ingest/parsers ──► ledger.db ──► metrics + profile + outcomes
                                      │                    │
                                      ▼                    ▼
                              live/server.py ◄──── dashboard (vanilla JS)
                                      │
                                      ├── SSE /v2/events (live refresh)
                                      ├── MCP stdio bridge (agent tools)
                                      └── optimize loop → instruction files
```

---

## Why Cairn

| Tool | What it does | What Cairn adds |
|------|--------------|-----------------|
| ccusage / Tokscale | Spend dashboards | + context profiling, fingerprint drift, measured optimize |
| ContextLens | Single-prompt profiling | Multi-agent, from local logs, no proxy |
| AgentAssay | Behavioral fingerprinting | Productized dashboard + drift alerts |
| Self-improvement CLIs | Propose instruction edits | **Measures** whether edits actually helped |

Nobody else combines all five pillars and closes the loop with holdout measurement.

---

## Privacy

Local-first. Ledger and dashboard stay on disk / `127.0.0.1`. No telemetry, no accounts, no cloud sync. Export bundles are scrubbed of common secret patterns.

---

## Install

```bash
curl -LsSf https://cairn.dev/install.sh | sh   # optional installer
pip install cairn-workspace
uv tool install cairn-workspace
```

Requires Python 3.11+. Runtime deps: `httpx` (optional LLM reflector), `numpy` (fingerprint math).

---

## Documentation

- [Getting started](docs/getting-started.md)
- [Concepts](docs/concepts.md)
- [CLI reference](docs/reference/cli.md)
- [Agent capture](docs/guides/agent-capture.md)
- [Dashboard](docs/guides/dashboard.md)
- [Optimize loop](docs/guides/optimize.md)
- [CI gates](docs/guides/ci.md)

---

## Development

```bash
git clone https://github.com/Harsh-Daga/Cairn.git && cd Cairn
pip install -e ".[dev]"
python3 -m pytest tests/ -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md).
