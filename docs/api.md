# API overview

Cairn serves a FastAPI application from `server/app.py`. All JSON routes use the `/api` prefix unless noted. OpenAPI docs are at `/api/docs` when the server is running.

Start the server with `cairn ui` (default `http://127.0.0.1:8787`).

## Health and docs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | `{ "status": "ok", "version": "1.0.0" }` |
| GET | `/api/docs` | Swagger UI |
| GET | `/api/openapi.json` | OpenAPI schema (also used to generate UI types) |

## Workspace

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/workspace` | Workspace metadata, adapter status, token gauge, health |

## Overview and analytics

| Method | Path | Query params | Description |
|--------|------|--------------|-------------|
| GET | `/api/overview` | `days` (default 30) | KPIs, narrative sentences, sparkline data |
| GET | `/api/agents` | `days` | Per-agent usage and handoff matrix |
| GET | `/api/behavior` | `days` | Fingerprint series and drift points |
| GET | `/api/quality` | `days` | Outcome scores, cost-per-success |
| GET | `/api/analytics/usage` | `days`, `group_by` | Usage grouped by day/model/source/project/actor |
| GET | `/api/analytics/regions` | `days` | Context region breakdown |
| GET | `/api/analytics/waste` | `days` | Waste taxonomy totals |
| GET | `/api/analytics/tail` | `days` | Tail latency / long-span stats |

## Traces

Prefix: `/api/traces`

| Method | Path | Query params | Description |
|--------|------|--------------|-------------|
| GET | `/api/traces` | `days`, `source`, `project`, `actor`, `q`, `limit`, `offset` | Paginated trace list |
| GET | `/api/traces/{trace_id}` | — | Trace detail, span tree, metadata |
| GET | `/api/traces/{trace_id}/replay` | `seq` | Spans visible at replay sequence (scrubber) |

## Insights

Prefix: `/api/insights`

| Method | Path | Query params | Description |
|--------|------|--------------|-------------|
| GET | `/api/insights` | `state`, `limit` | Detector insights by lifecycle state |
| GET | `/api/insights/{insight_id}/evidence` | — | Evidence chain for an insight |

## Experiments (optimize)

Prefix: `/api/experiments`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/experiments` | All improvement experiments |
| GET | `/api/experiments/{experiment_id}` | Experiment detail, measurement, verdict |

## Search

Prefix: `/api/search`

| Method | Path | Query params | Description |
|--------|------|--------------|-------------|
| GET | `/api/search` | `q`, `limit` | Full-text search across span payloads |

Example queries: `pytest`, `tool:read`, `source:claude_code`, `is:error`.

## Actions (mutations)

Prefix: `/api/actions`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/actions` | Action manifest (name, params schema, async flag) |
| POST | `/api/actions/{name}` | Run a registered action; returns `{ ok, result }` or `{ ok, job_id }` for async jobs |

Registered actions (from `server/api/actions.py`):

| Action | Category | Async | CLI equivalent |
|--------|----------|-------|----------------|
| `sync` | ingest | yes | `cairn sync` |
| `backfill` | ingest | yes | `cairn action backfill` |
| `rebuild_view` | analyze | yes | `cairn rebuild --view …` |
| `check` | ci | no | `cairn check` |
| `export_bundle` | export | no | `cairn export` |
| `mcp_install` | setup | no | `cairn mcp install` |
| `optimize_propose` | improve | no | `cairn optimize` |
| `experiment_apply` | improve | no | — |
| `experiment_revert` | improve | no | `cairn experiments revert ID` |
| `experiment_measure` | improve | no | — |
| `insight_set_state` | insights | no | — |
| `annotate` | annotate | no | — |
| `workspace_scan` | setup | yes | — |
| `config_set` | config | no | `cairn config set KEY VALUE` |
| `server_stop` | server | no | `cairn stop` |

## Live events (SSE)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/live/events` | Server-sent events stream (ingest, insight, job updates) |

The UI connects via `ui/src/lib/sse.ts` when **Watch** is enabled on the Live page.

## OTLP ingest

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/traces` | Accept OTLP/JSON or protobuf trace payloads (not under `/api`) |

See [OTLP ingest](otlp.md) for content types, examples, and idempotency behavior.

## Static UI

Non-API paths serve the built React app from `server/static/` (produced by `scripts/build_ui.py`). Unknown `/api/*` paths return 404 JSON; all other paths fall back to `index.html`.

## Auth

By default the server binds to loopback only. To bind elsewhere, pass `--token` to `cairn ui` and set `CAIRN_TOKEN`. Non-loopback bind without a token is refused at startup.

## Error shape

HTTP errors return JSON:

```json
{ "error": { "code": "not_found", "message": "…" } }
```

FastAPI validation errors use standard `detail` arrays.
