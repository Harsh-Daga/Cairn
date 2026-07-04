# Cairn v3 charter

## Mission

Cairn is the local-first self-analyzing platform for AI coding agents. It profiles context waste, fingerprints behavior, anchors quality to outcomes, and measures whether instruction changes actually helped.

## Scope (in)

| Area | Module | Responsibility |
|------|--------|----------------|
| Ingest | `cairn/ingest/` | Detect agents, parse logs, write ledger |
| Ledger | `cairn/ledger/` | SQLite schema v4, migrations |
| Metrics | `cairn/metrics/` | Rollups, waste, fingerprints |
| Profile | `cairn/profile/` | Context decomposition + detectors |
| Outcomes | `cairn/outcomes/` | Git/tests quality scoring |
| Optimize | `cairn/optimize/` | Evidence, proposals, holdout measurement |
| MCP | `cairn/mcp/` | Agent self-awareness tools |
| Live UI | `cairn/live/` + `cairn/assets/` | Dashboard, API, SSE |
| CLI | `cairn/cli/main.py` | Power-user mirror of UI actions |

## Scope (out)

- Cloud sync, accounts, telemetry
- Running agents or calling model APIs (except optional optimize reflector via `httpx`)
- pydantic, fastapi, jinja2, graph workflow engines

## Hard rules

- **UI-first**: every capability is operable from the dashboard
- **Local-first**: `127.0.0.1` server, on-disk ledger
- **Stdlib-first**: Python ≥3.11; runtime deps `httpx` + `numpy` only
- **Honest data**: NULL + data-notes when fields are absent; never fabricate zeros

## v3 pillars map

1. Context profiling → `profile/`, `metrics/waste.py`
2. Fingerprinting → `metrics/fingerprint.py`
3. Outcomes → `outcomes/`
4. Optimize loop → `optimize/`
5. MCP → `mcp/`

## Success criteria

- `cairn` golden path works with zero config
- Cursor sessions show real timestamps and token data
- Optimize proves before/after on holdout
- `python3 -m pytest tests/ -q` green
