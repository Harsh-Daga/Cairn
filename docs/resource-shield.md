# Resource shield

Cairn reports measured local resource use without claiming idle-soak or multi-hour
stability until scheduled benchmarks land.

## Inventory

`cairn resource` / `cairn resource --json` (`cairn.resource.v1`) breaks out:

- SQLite database, WAL, and SHM
- exports, backups, regressions, receipts cache, static exports
- other files under `.cairn`
- optional soft budget from `[resources].soft_budget_bytes`
- descriptive growth from recent span volume (not a confidence-bounded forecast)
- best-effort process RSS for the current CLI/API process

Workspace API embeds a compact `resources` object. Overview and session Resource
shields use the same inventory when a workspace root is available.

Settings → **Resource & Privacy** surfaces the inventory, storage mode, strip preview/apply,
lifecycle dry-run, backup/list/restore, integrity, compact, git exclude, egress, and circuit
status over the same actions as the CLI. Restore lists `.cairn/backups/manual`, runs a dry-run
preview, then requires typing `RESTORE` plus
`[lifecycle].destructive_enabled` before replacing the live ledger. There is no FTS index to
rebuild after ADR 0012.

## Soft budget

Configure with:

```bash
cairn config set resources.soft_budget_bytes 1073741824 --scope workspace
```

`cairn doctor` warns (fails the disk check) when the measured total exceeds the soft
budget. Compaction and deletion still require explicit confirmation via lifecycle actions.

## Circuit breakers (ingest)

Before `adapter.parse_path`, Cairn enforces:

| Budget | Config | Default |
| --- | --- | --- |
| Max source file size | `resources.max_file_bytes` | 32 MiB |
| Parse wall-clock | `resources.max_parse_ms` | 30s |
| Consecutive failures → pause | `resources.max_consecutive_failures` | 5 |

Violations write scrubbed quarantine metadata under `.cairn/quarantine/` and never rewrite
agent source logs. Soft budget `over` pauses ingest globally until space is freed and
`circuit_resume` is run.

```bash
cairn action circuit_status
cairn action circuit_resume
cairn action circuit_resume --params-json '{"adapter_id":"cursor"}'
```

Shield states include `healthy`, `degraded`, `paused`, `quarantined`, `attention`,
`unknown`, and `unavailable`.

## Watcher (auto-sync)

Backend watching uses a single coalesced queue path (no synchronous callback ingest):

- path-level coalescing and burst debounce
- adaptive idle poll backoff (measured locally; not a soak claim)
- per-cycle path/change caps so large historical sets yield
- stale missing-path pruning on rediscovery

Collection status exposes `watcher.paths_checked`, `paths_deferred`, `changed_files`,
`dropped_events`, and `event_path: "queue"`.

## Separation of controls

- **Collection mode** (`[collection].mode`) — backend auto-sync
- **Live updates** — browser SSE only
- **Resource inventory** — disk/process accounting above

These are independent. See also [configuration.md](configuration.md) and
[performance.md](performance.md).
