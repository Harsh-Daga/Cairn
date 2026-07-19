# Watcher and ingest discovery

Backend auto-sync uses a polling watcher with a **single coalesced event path**.
There is no synchronous callback ingest alongside the queue.

## Contracts

| Concern | Behavior |
|---------|----------|
| Event path | `FileWatcher.events()` → pipeline `_event_loop` only |
| Coalescing | Pending map + queue drain keep one newest event per path |
| Catch-up | Cap paths and changes checked per poll; rotate through the set |
| Stale watches | `watch()` replaces the set; missing paths prune after repeated misses |
| Idle backoff | Poll interval grows while unchanged (capped); not a soak claim |
| Active sessions | Recently touched paths are ordered first under pressure |
| Discovery vs parse | Refresh rediscovers adapter streams; watcher only stats known paths |

Native OS file events are not required. Adaptive polling is the tested fallback.

## Status

`IngestPipeline.status()["watcher"]` exposes measured facts: paths checked/deferred,
changed/missing/pruned counts, duration, poll interval, and dropped events.

Collection mode (`manual` / `efficient` / `live`) remains independent of browser SSE
Live updates. See [resource-shield.md](../resource-shield.md).
