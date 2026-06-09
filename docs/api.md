# Cairn HTTP API

Local v1 API served by `cairn api serve` (default `127.0.0.1:8790`).

## OpenAPI

```
GET /v1/openapi.json
```

Returns the machine-readable OpenAPI 3.0 specification.

## Authentication

When `CAIRN_API_TOKEN` is set, all routes require:

```
Authorization: Bearer <token>
```

## Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/projects/{project_id}/sessions` | List capture sessions |
| GET | `/v1/sessions/{session_id}` | Session detail (+ trajectory mirror when present) |
| GET | `/v1/sessions/{session_id}/events` | SSE stream (`append`, `finish` events) |
| POST | `/v1/workflows/{workflow_id}/run` | Execute workflow (JSON body: `dry_run`, `yes`, `provider_mode`) |
| GET | `/v1/runs/{run_id}/report` | Unified observability report JSON |

`project_id` is the basename of the opened project root (e.g. `my-project`).

## Examples

```bash
export CAIRN_API_TOKEN=dev
uv run cairn api serve --port 8790

curl -H "Authorization: Bearer dev" \
  http://127.0.0.1:8790/v1/projects/my-project/sessions

curl -H "Authorization: Bearer dev" \
  http://127.0.0.1:8790/v1/sessions/sess-redacted-001

curl -N -H "Authorization: Bearer dev" \
  http://127.0.0.1:8790/v1/sessions/sess-redacted-001/events

curl -X POST -H "Authorization: Bearer dev" -H "Content-Type: application/json" \
  -d '{"dry_run": true}' \
  http://127.0.0.1:8790/v1/workflows/default/run
```

## Live UI vs API

- `cairn live serve` (port 8787) — capture bundle HTML + SSE for browsers
- `cairn api serve` (port 8790) — JSON/SSE API for automation and integrations

Both bind to localhost by default.
