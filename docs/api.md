# HTTP API

Cairn exposes a local v1 HTTP API for automation and integrations. Start it with:

```bash
cairn api serve --port 8790
```

Default bind address: `127.0.0.1` (local only).

## OpenAPI

Machine-readable specification:

```
GET /v1/openapi.json
```

Use this to generate clients or explore routes in Swagger UI.

## Authentication

When `CAIRN_API_TOKEN` is set in the environment, every route requires:

```
Authorization: Bearer <token>
```

If the variable is unset, the API accepts unauthenticated requests on localhost.

## Routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/projects/{project_id}/sessions` | List capture sessions |
| `GET` | `/v1/sessions/{session_id}` | Session detail |
| `GET` | `/v1/sessions/{session_id}/events` | SSE stream (`append`, `finish` events) |
| `POST` | `/v1/workflows/{workflow_id}/run` | Execute workflow |
| `GET` | `/v1/runs/{run_id}/report` | Unified observability report (JSON) |

`project_id` is the basename of the opened project directory (e.g. `my-project` for
`/home/user/my-project`).

### Run workflow (POST body)

```json
{
  "dry_run": false,
  "yes": true,
  "provider_mode": "recorded"
}
```

## Examples

```bash
export CAIRN_API_TOKEN=dev
cairn api serve --port 8790

# List sessions
curl -s -H "Authorization: Bearer dev" \
  http://127.0.0.1:8790/v1/projects/my-project/sessions | jq .

# Session detail
curl -s -H "Authorization: Bearer dev" \
  http://127.0.0.1:8790/v1/sessions/sess-redacted-001 | jq .

# Live event stream
curl -N -H "Authorization: Bearer dev" \
  http://127.0.0.1:8790/v1/sessions/sess-redacted-001/events

# Dry-run workflow
curl -s -X POST \
  -H "Authorization: Bearer dev" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}' \
  http://127.0.0.1:8790/v1/workflows/default/run | jq .

# Run report
curl -s -H "Authorization: Bearer dev" \
  http://127.0.0.1:8790/v1/runs/<run_id>/report | jq .
```

## Live UI vs API

| Service | Port | Purpose |
|---------|------|---------|
| `cairn live serve` | 8787 (default) | Browser HTML bundle + SSE |
| `cairn api serve` | 8790 (default) | JSON/SSE for scripts and integrations |

Both bind to localhost by default. See [Security](security.md) before exposing beyond your machine.
