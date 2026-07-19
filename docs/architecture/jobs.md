# Bounded job executor

Long-running actions (`sync`, `backfill`, `rebuild_view`, `workspace_scan`) run on a
**bounded** in-process executor — not unbounded thread-per-job spawning.

## Contracts

| Concern | Behavior |
|---------|----------|
| Workers | `[jobs].max_workers` (default 2) |
| Queue | `[jobs].max_queued` pending+running; excess → HTTP 429 `job_saturated` |
| Dedupe | One active `sync` / `backfill` per workspace runner |
| Progress | SSE `job-progress` + `GET /api/actions/jobs/{id}` |
| Cancel | `POST /api/actions/jobs/{id}/cancel` (cooperative; handlers check handle) |
| Timeout | Soft/default `[jobs].default_timeout_sec`; checked on progress ticks |
| Expiry | Finished results pruned after `[jobs].result_ttl_sec` |
| Shutdown | Lifespan cancels pending and shuts down the pool |

Jobs are in-memory only. Cancellation cannot forcibly kill a non-cooperative handler.

## Configuration

```toml
[jobs]
max_workers = 2
max_queued = 8
result_ttl_sec = 3600
default_timeout_sec = 900
```
