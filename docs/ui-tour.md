# UI tour

The Cairn **field notebook** UI lives in `ui/` and is served by `cairn ui` at `http://127.0.0.1:8787`. Navigation is in the left **Waypoint rail**; Settings sits at the bottom. Thirteen pages map to the routes in `ui/src/router.tsx`.

## 1. Overview (`/`)

**Question:** *What happened, and what should I look at?*

- Narrative sentences summarize recent activity; click a sentence to jump to filtered Sessions.
- KPI cards: sessions, spend, input tokens, waste tokens.
- Quick links to Insights, Optimize, and high-waste sessions.
- Empty state prompts `cairn sync`.

## 2. Sessions (`/sessions`)

**Question:** *Find the session that matters.*

- Sortable table of traces with source, cost, tokens, title, and relative time.
- Respects global time range and URL filters (`?days=`, `?source=`, `?q=`).
- Click a row to open Session detail.

## 3. Session diff (`/sessions/diff`)

**Question:** *How did two sessions differ?*

- Compare two selected sessions side by side from the Sessions page.
- The command palette also provides a **Session diff** entry.

## 4. Session detail (`/sessions/:id`)

**Question:** *What happened turn by turn?*

- **Waterfall** — span tree with subagent swimlanes (dagre layout).
- **Replay scrubber** — step through turns via `?seq=`; fetches `/api/traces/{id}/replay`.
- **Span inspector** — select a span for payload, regions, and waste tags.
- **Context timeline** — region fill over the session.

## 5. Context (`/context`)

**Question:** *What filled the context window, what repeated, and where can waste be cut?*

- Stacked region breakdown (system, tool schema, tool results, retrieved, user, history).
- Waste analytics with categorized span events plus an explicit uncategorized remainder, reconciled
  to the session-level waste total.
- Data from `/api/analytics/regions` and `/api/analytics/waste`.

## 6. Agents (`/agents`)

**Question:** *Who's doing what, and how do they handoff?*

- Per-actor usage table (main agent vs subagents when lineage exists).
- Handoff matrix showing transitions between actors.
- Links to filtered Sessions per agent.

## 7. Behavior (`/behavior`)

**Question:** *Has my agent changed?*

- Fingerprint radar and control chart over the selected window.
- Drift alerts when AMDM detects behavioral change.
- Needs ~10 fingerprinted sessions; empty state explains the threshold.

## 8. Quality (`/quality`)

**Question:** *Is the work actually good, and what does success cost?*

- Outcome scores, lucky-pass flags, cost-per-success bars.
- Enable outcome capture from Settings or `config_set` when no outcomes exist.
- Data from `/api/quality`.

## 9. Insights (`/insights`)

**Question:** *What should I fix?*

- Kanban grouped by lifecycle: New → Acknowledged → Fixed → Regressed.
- Expand a card for evidence; **Ack** with undo toast.
- Badge count on the rail for new insights.
- Evidence chain via `/api/insights/{id}/evidence`.

## 10. Optimize (`/optimize`)

**Question:** *Close the loop: propose → apply → measure → verdict.*

- Station board: Proposed → Applied → Measuring → Verdict.
- **Apply** / **Revert** per experiment (calls `experiment_apply` / `experiment_revert`).
- Copper dot on the rail when proposals are pending.
- See [Optimize loop](optimize.md).

## 11. Live (`/live`)

**Question:** *What's happening right now?*

- SSE stream from `/api/live/events` is enabled by default and can be paused with the **Watch** topbar toggle.
- Pulsing badge on the rail while watching.
- Pause, dropped-event counter, links to traces as events arrive.

## 12. Search (`/search`)

**Question:** *Find anything across sessions.*

- Debounced full-text search via `/api/search`.
- Example chips: `pytest`, `tool:read`, `source:claude_code`, `is:error`.
- Results grouped by trace with highlighted snippets.

## 13. Settings (`/settings`)

**Question:** *See what Cairn sees; change what it does.*

- **Workspace** — name, root path, session count.
- **Adapters** — source, stream count, last ingest; **Rescan adapters**.
- **Data** — Sync now, export scrubbed bundle, rebuild views (type `rebuild` to confirm).
- **MCP** — copy install snippet for agent clients.
- Token **gauge** in the rail footer when plan limits are configured.

## Global chrome

- **Plaque topbar** — time range (7d / 30d / 90d), Sync, Watch toggle, command palette (`⌘K`).
- **Command palette** — quick navigation and actions mirroring the CLI action registry.
- **Toasts** — undo for insight ack and other reversible actions.

Every button that mutates state calls `POST /api/actions/{name}` — the same handlers as the CLI.
