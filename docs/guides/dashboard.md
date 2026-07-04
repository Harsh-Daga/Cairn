# Dashboard guide

## Start the server

```bash
cairn                    # golden path: sync + dashboard (background)
cairn --foreground       # keep server in terminal
cairn dash --port 8788   # explicit port
cairn stop               # stop background server
```

Opens `http://127.0.0.1:8787` by default.

## Waypoint pages

| Page | Content |
|------|---------|
| Overview | Narrative hero, KPIs with confidence chips, recent sessions, spend treemap |
| Context | Strata chart, recoverable $/wk, findings |
| Behavior | Fingerprint radar, drift alerts |
| Quality | Outcome funnel, cost-per-success |
| Charts | Cost, tokens, waste, context pressure |
| Insights | 12 evidence-backed rules (legacy + difficulty-aware), drill-down links |
| Optimize | Proposals, apply/revert, impact bars |
| Sessions | Full table with **Export** per row |
| Search | FTS over prompts and tool output |
| Settings | Config, sync, backfill, check, MCP |

## Export

On the **Sessions** page, click **Export** on any row for a scrubbed self-contained HTML bundle (same as `cairn share ID`).

## SSE live refresh

Toggle **Watch** in the topbar. The dashboard subscribes to `/v2/events` for `metrics-updated` and `optimize-proposals`. Cursor `state.vscdb` changes trigger incremental re-ingest and SSE push.

## MCP

On first load, Cairn auto-installs MCP config for detected clients (Claude Code, Cursor, Codex). Disable via Settings → MCP → `auto_install`.

## Plan-window gauge

Sidebar shows Codex 5-hour rate limit or context-fill for other agents. Override via `limits.five_hour_tokens` in config.

## Static bundle

```bash
cairn share SESSION_ID -o bundle.html
```

Works at `file://` — same assets as the live server.

## Narrative hero & session autopsy (2.0)

**Overview** leads with a plain-English headline from `/api/overview` → `narrative` (headline, clickable sentences, one CTA). KPI numbers show **confidence chips** (`±N% est.`) when token/cost data is estimated, not exact.

**Session detail** (`/session.html?id=…`) opens with an **autopsy** panel when diagnostics exist: outcome/failure badges, trajectory timeline (failure-origin marker, cascade blast shading), ideal-path savings, and optional git rewind suggestion (text only — never auto-run). Sessions without diagnostics show an honest “not enough signal” message.

Regression tests in `tests/test_frontend_wiring.py` assert every backend payload field has a matching consumer in `dashboard.js` / `session.js`.
