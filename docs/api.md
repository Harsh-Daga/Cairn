# API overview

Cairn serves a FastAPI application from `server/app.py`. All JSON routes use the `/api` prefix unless noted. OpenAPI docs are at `/api/docs` when the server is running.

Start the server with `cairn ui` (default `http://127.0.0.1:8787`).

## Health and docs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | `{ "status": "ok", "version": "1.1.1" }` |
| GET | `/api/docs` | Swagger UI |
| GET | `/api/openapi.json` | OpenAPI schema (also used to generate UI types) |

## Workspace

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/workspace` | Workspace metadata, adapter status, token gauge, health |

## Overview and analytics

| Method | Path | Query params | Description |
|--------|------|--------------|-------------|
| GET | `/api/overview` | time range | KPIs, narrative sentences, sparkline data |
| GET | `/api/agents` | time range | Per-agent usage and handoff matrix |
| GET | `/api/behavior` | time range | Fingerprint series and drift points |
| GET | `/api/quality` | time range | Outcome scores, cost-per-success |
| GET | `/api/analytics/usage` | time range, `group_by` | Usage grouped by day/model/source/project/actor |
| GET | `/api/analytics/regions` | time range | Context region breakdown |
| GET | `/api/analytics/waste` | time range | Waste taxonomy totals |
| GET | `/api/analytics/tail` | time range | Tail latency / long-span stats |

“Time range” means one of `preset`, complete `start`/`end` plus `timezone`, or legacy `days`. See
[Time ranges and timezones](time-ranges.md) for exact half-open and prior-period semantics.

## Traces

Prefix: `/api/traces`

| Method | Path | Query params | Description |
|--------|------|--------------|-------------|
| GET | `/api/traces` | time range, `source`, `project`, `actor`, `q`, `sort`, `limit`, `offset` | Paginated enriched trace list |
| GET | `/api/traces/{trace_id}` | — | Trace detail, span tree, quality outcome, metadata |
| PUT | `/api/traces/{trace_id}/human-label` | JSON body | Store/clear thumbs label and note |
| GET | `/api/traces/{trace_id}/replay` | `seq` | Spans visible at replay sequence (scrubber) |
| GET | `/api/traces/{trace_id}/receipt` | — | Deterministic verification receipt v1 |
| GET | `/api/traces/{trace_id}/corrections` | — | Conservative correction ledger (`cairn.corrections.v1`) |
| PUT | `/api/traces/{trace_id}/corrections/{id}/relabel` | body | Local incorrect-classification override |
| GET | `/api/traces/{trace_id}/handoff` | — | Offline handoff capsule (`cairn.handoff.v1`) |
| GET | `/api/traces/{trace_id}/postmortem` | — | Diagnose-cascade postmortem when eligible |

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
| GET | `/api/search` | `q`, `limit`, `offset` | Bounded grouped search across traces and spans |

Sessions and Search use one typed grammar. Its generated machine-readable operator manifest is
[`docs/api/filter-grammar.json`](api/filter-grammar.json). Examples include `pytest`,
`tool:read`, `source:claude_code`, `is:error`, `cost:>1`, `file:"src/app.py"`, and
`verification:debt`. Quoted values and backslash escaping are supported. Invalid and
recognized-but-unavailable filters are returned in `filter_errors` and produce no rows, so a
malformed privacy or evidence constraint never broadens a query.

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
| GET | `/api/live/events` | Server-sent events stream (ingest, insight, job, cost-tick updates) |

The UI connects via `ui/src/lib/sse.ts` when **Watch** is enabled on the Live page.

Named events include `trace-updated`, `views-updated`, `insight-updated`, `job-progress`,
`heartbeat`, and coalesced `session_cost_tick`. Cost ticks carry absolute `cost`, token totals,
`cost_source`, and `estimate_kind` (`measured` / `estimated` / `unavailable`). The server publishes
at most one tick per session every two seconds, coalesces bursts to the latest totals, suppresses
duplicate totals, and uses the shared drop-oldest SSE queue (size 64).

## OTLP ingest

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/traces` | Accept OTLP/JSON or protobuf trace payloads (not under `/api`) |

See [OTLP ingest](otlp.md) for content types, examples, and idempotency behavior.

## Static UI

Non-API paths serve the built React app from `server/static/` (produced by `scripts/build_ui.py`). Unknown `/api/*` paths return 404 JSON; all other paths fall back to `index.html`.

## Auth

By default the server binds to loopback only. To bind elsewhere, pass `--token` to `cairn ui`. Every route then requires either `Authorization: Bearer <token>` or the `cairn_token` browser cookie. Opening `http://HOST:PORT/?token=<token>` establishes that HttpOnly cookie and redirects to the token-free URL. Non-loopback bind without a token is refused at startup.

## Error shape

HTTP errors return JSON:

```json
{ "error": { "code": "not_found", "message": "…" } }
```

Validation errors use the same envelope with code `validation_error` and a bounded `details` list.
