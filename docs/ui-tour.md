# UI tour

The Cairn **field notebook** UI lives in `ui/` and is served by `cairn ui` at
`http://127.0.0.1:8787`. The desktop **Waypoint rail** and horizontally scrollable mobile dock
share one route registry, so neither surface silently drops a working route.

The rail groups current working routes by intent:

- **Monitor** — Overview, Live, Sessions.
- **Analyze** — Context, Tools, Files, Compare, Agents, Behavior, Quality.
- **Act** — Insights, Optimize, Guard.
- **Utilities** — Search, Settings.

Weekly Recap is a working palette-only route linked from Overview, so it does not crowd the rail.
Cairn does not publish dead navigation or placeholder product shells.

## 1. Overview (`/`)

**Question:** _What did this range cost, what did success cost, and what needs attention next?_

- The money-and-quality hero follows the selected global range. It shows measured/estimated spend,
  conservatively allocated avoidable spend, outcome quality and sample size, cost per successful
  session, and equal-length prior-period deltas. Month-end uses shared burn math: linear projection
  plus trailing-seven-day when history allows; projected overrun date only with ≥7 active days and
  a positive linear rate inside the calendar month (workspace timezone). Historical ranges omit
  projections. Configured monthly/weekly/daily ceilings feed budget state.
- Verification, Scope, Privacy, and Resource are four independent shield cards. Each exposes a
  state, facts, limitation, and real destination; Cairn never combines them into a universal trust
  score or calls an unmeasured shield healthy.
- The three largest priced waste causes include a plain-language cause, conservative impact,
  concrete fix, and **Review fix** action. **Evidence** opens a keyboard-contained side panel with
  at most five exact supporting session/span links, relative paths where available, and the impact
  calculation limitation. Imported text is displayed only as untrusted evidence.
- Stat tiles are sessions, spend, waste rate, and quality. Sparklines are decorative summaries of
  adjacent text values; equal-period comparisons come from the Overview API rather than splitting
  the current chart window in the browser.
- Cost over time has an equivalent native table and keyboard point inspection. Applied experiment
  annotations link to the exact expanded Optimize experiment. Guard instruction-edit annotations
  deep-link to `/guard?event=…` when events exist in range.
- Needs attention separately reports failed outcomes, successful outcomes lacking recorded
  test/build evidence, active drift signals, retry storms, adapter parse degradation, and
  projected budget risk. Claim support and rule decay remain visibly **unavailable** until their
  evidence-producing tracker rows land. Every reported item links to its exact session/span,
  insight, or corrective settings surface.
- Loading, disconnected, no-workspace-data, and no-results-in-selected-range states are distinct.
  At narrow widths sections stack without hiding data; charts retain their table alternatives.
  Static snapshots use the captured Overview/usage/waste/tail/recap payloads and do not invent live
  state or unsupported custom ranges.

Running bare `cairn` performs a sync, prints this same 30-day money summary in the terminal,
then opens the local UI. Sessions without reliable cost data remain excluded from dollar
allocation and are called out in the existing data notes.

Overview shows a local weekly recap banner with spend, estimated waste, the top cause, quality
movement, and experiment-verdict count. Dismissal stores only the UTC Monday period key in browser
storage, so the next weekly period reappears instead of being permanently hidden. The complete
working route is available at `/recap` and from the command palette. The same one-screen summary
is available with `cairn recap`; it reads the local ledger and makes no network call.

`cairn recap --share` writes a 1200×630 “Agent Wrapped” SVG and PNG under
`.cairn/recaps/` (or `--output`). The default card includes aggregate spend, estimated waste,
a privacy-safe file-type label for the most re-read file, a generalized repeat-failure joke,
and an archetype derived from fingerprint ratios. Raw paths, commands, code, and repository
names never enter the default render payload. `--show-repo` opts in only the workspace display
name; rendering and file writes remain entirely local.

## 2. Sessions (`/sessions`)

**Question:** _Which bounded set of sessions should I investigate or compare?_

- The server-paginated, virtualized table shows title, agent/source, start and duration, tokens with
  a flow sparkline when sampled calls exist, cost, waste, quality, outcome, verification state, and
  data-quality state. Only visible rows plus overscan are mounted; the API page remains capped at
  50.
- Expand **Preview** for the first user request, three most-used relative files, outcome, and data
  quality. Text remains plain React text, never HTML. Static exports replace first-request text and
  scrub relative paths.
- Stable URL-backed sorts cover recent, waste, cost, duration, tokens, and quality. Legacy
  `source`/`agent` parameters remain compatible.
- Sessions and Search share the generated typed grammar: quoted values and backslash escaping,
  `agent:`, `source:`, `cost:>`, `outcome:`, `file:`, `tool:`, `after:`, and `verification:`.
  Invalid tokens and evidence filters whose producer has not landed return explicit errors and zero
  rows; they never silently broaden a query. Parsed filters appear as keyboard-removable chips and
  browser autocomplete comes from the generated server operator manifest.
- Existing browser-local saved views retain their stored URL parameters. Select exactly two rows
  for Session Diff, or three through twenty for a descriptive multi-session cost/token/waste/
  quality/verification summary that makes no comparability or causal claim.
- `j`/`k` move the selected row and Enter opens it. Pagination, selection, sort, and typed filters
  are behavior-tested. **Copy privacy-safe filter link** excludes free text, file paths, and agent
  identifiers; no private query content is sent elsewhere.
- Static snapshots retain the captured preset/default pages and explicitly reject uncaptured
  filters or pages rather than showing a misleading empty result.

## 3. Session diff (`/sessions/diff`)

**Question:** _How did two sessions differ?_

- Open two selected sessions side by side from the Sessions page (not the Analyze → Compare
  difficulty ledger). The response preserves the existing aligned-turn diff and adds signed
  cost/token/waste/quality/duration totals, context regions, models, outcomes, and recorded
  diagnose fields.
- **Comparison validity** reports same/different source, project, task-title, and difficulty facts.
  A limited or not-comparable state keeps descriptive deltas visible but never presents them as a
  causal or fair performance comparison.
- **What changed** statements link to the exact session or failure-origin span supporting each
  recorded delta. The aligned timeline progressively renders large results and labels bounded
  position alignment when quadratic LCS would be unsafe.
- Static snapshots capture up to ten adjacent recent pairs. Other pairs fail with the standard
  uncaptured-view explanation rather than a misleading empty comparison.
- The command palette provides a **Session diff** entry for this route.

## 4. Session detail (`/sessions/:id`)

**Question:** _What happened turn by turn?_

- **Waterfall** — span tree with subagent swimlanes (dagre layout).
- **MCP consultations** — privacy-safe “agent consulted Cairn here” markers show where a live
  agent used Cairn; no MCP arguments, paths, prompts, code, or results are stored.
- **Replay** — step, play, or pause at 1×/4×/16× via stable `?seq=` links; the synchronized
  summary shows context, files, and actors using `/api/traces/{id}/replay`.
- **Investigation** — a virtualized token/time waterfall keeps span, zoom, retry/handoff links,
  errors, duration, token, and MCP consultation evidence addressable. `j`/`k` traverses spans and
  Escape closes the active zoom or inspector selection.
- **Inspector and minimap** — Summary, Content, Context, and Links views remain plain-text and the
  minimap has pointer-independent previous/next viewport controls.
- **Transcript, Receipt, Corrections, Post-mortem** — URL-backed `?tab=` views separate retained
  conversation/tool text from verification evidence. Receipt is versioned `cairn.receipt.v1` from
  recorded outcomes/spans (status, transparent debt weights, timeline); claims stay empty with an
  explicit limitation. Corrections shows high-precision phrase classifications with recovery status
  (`cairn.corrections.v1`); absence of matches is not zero supervision tax. Post-mortem shows
  diagnose-cascade steps, uncertainty, span deep links, and Copy Markdown when a failed/low-quality
  session qualifies; it never claims causality.
- **Independent shields** — Verification, Scope, Privacy, and Resource facts retain their own
  state and limitation. Active traces are marked as live and refreshed every two seconds.
- **Actions** — preselect the trace for comparison, open the recorded post-mortem, copy the exact
  local deep link, or write a scrubbed owner-local evidence bundle. Static snapshots disable the
  mutating export action.

## 5. Context (`/context`)

**Question:** _Where your tokens go, what repeats, and what remains measurable?_

- An answer-first **context ledger** from `/api/analytics/regions` states a deterministic conclusion,
  mapped-token and re-bill ratios, region coverage, an explicit next action, and the limitation that
  mapped rows are not a partition of input tokens and do not prove avoidable spend.
- Region composition and timezone-aware daily trend use `ChartFrame` with a native data table.
  Unmapped input is never inferred into a region.
- Top re-billed blocks rank same-hash repetition after one retained copy, with estimated tokens,
  suggested fix, and one exact session/span evidence link. Estimates stay labeled.
- Cache-hit trend shows recorded counters and hit ratio when measured; **estimated dollar savings
  stay unavailable** unless provider billing semantics are established.
- Per-agent mapped-token comparison and per-adapter region/cache coverage (plus dropped events)
  keep data-quality visible.
- Waste analytics remain categorized span events reconciled to the session-level waste total via
  `/api/analytics/waste`.
- Static snapshots capture the same regions/waste payloads for supported `days` presets.

## 6. Tools (`/tools`)

**Question:** _Which tools run, fail, retry, and tax the schema?_

- Answer-first tool ledger from `/api/analytics/tools` with normalized identity, error/retry rates,
  schema-overhead tokens, and an evidence-linked next action.
- Per-tool invocations, sessions, success/error/cancelled rates, median/p95 latency, result tokens,
  and token-proportional estimated cost share (explicitly estimated).
- Families distinguish built-in, MCP, shell, and unknown tools via the shared ingest taxonomy.
- Failure samples and worst-session evidence stay one click from Session Detail.
- Adapter coverage reports tool-session share plus distinct/mapped tool counts.
- Unused-schema tax uses mapped `tool_schema` region tokens and is not invented per tool.

## 7. Files (`/files`)

**Question:** _Which paths are read, re-read, edited, and churned?_

- Answer-first file ledger from `/api/analytics/files` with distinct paths, reads/re-reads/edits,
  revert/fixup session counts, and ignored-prefix flags.
- Hottest-path ranking and timezone-aware read/edit/re-read churn use `ChartFrame` tables.
- Evidence links stay session/span exact. Absolute and home paths are dropped server-side.
- Rename/delete completeness is still limited for non-instruction paths; instruction-file renames
  appear on Guard.

## 8. Compare (`/compare`)

**Question:** _Which agent performs best for this repository and task difficulty?_

- Answer-first compare ledger from `/api/analytics/compare` groups primary-agent sessions by
  difficulty bucket and reports cost/tokens/quality/waste, retry rate, cost/success, verification
  debt, verified-success rate, and correction burden with anytime-valid intervals.
- Pairwise cost-per-session views stay within a difficulty bucket and surface model/source confound
  warnings. No overall winner is declared without n≥20, non-overlapping intervals, and clear
  confounds.
- Session Diff remains the turn-by-turn route from Sessions → Compare selected; this page never
  replaces matched-pair investigation.
- Static snapshots capture `/analytics/compare` for supported `days` presets.

## 9. Agents (`/agents`)

**Question:** _Who did the work, how did they hand off, and is the sample enough?_

- Answer-first agent ledger from `/api/agents` with agent count, multi-agent session count,
  handoffs, sample size, and an evidence-linked next action.
- Per-agent cards show spend, waste, quality mean with n, model mix, error sessions, and a
  fingerprint thumbnail when vectors exist.
- Attributed-spend chart and accessible handoff table accompany the handoff graph.
- Adapter parse-health coverage is shown with an explicit lifetime-counter limitation.
- No leaderboard winner is invented from insufficient samples.

## 10. Behavior (`/behavior`)

**Question:** _Has my agent changed relative to its local fingerprint baseline?_

- Answer-first behavior ledger from `/api/behavior` with fingerprint session count, drift events,
  baseline progress, primary radar axis, and an evidence-linked next action.
- Drift table shows kind, date/week, sample size, magnitude, affected axes, and session links.
  Nearby instruction-file edits are listed on Guard when present for the range.
- Labeled radar keeps a native table alternative. EWMA trend stays visible; the control chart is
  on demand.
- Joint-shock detection still requires 20 matched project/model baseline sessions and never
  presents an incomplete baseline as “no drift.”

## 11. Quality (`/quality`)

**Question:** _Is the work actually good, and what does success cost?_

- Answer-first quality ledger from `/api/quality` separates process-quality score from task
  verification: verified completion, verification debt, mean cost/success, and lucky/unlucky
  investigation counts. Unsupported-claim rate stays explicitly unavailable until receipts land.
- Daily trend overlays quality mean with verified/debt rates and human up/down counts.
- Component breakdown, histogram, cost-per-success sparkline, calibration/coverage, and
  investigation evidence links accompany expandable per-session score details.
- Lucky-pass / unlucky-fail flags are descriptive heuristics only.
- Enable outcome capture from Settings or `config_set` when no outcomes exist.

## 12. Insights (`/insights`)

**Question:** _What should I fix?_

- Answer-first insights ledger from `/api/insights` ranks by impact, confidence, severity,
  recency, and recurrence. Overlapping detectors on the same primary evidence trace are
  suppressed; snoozed cards stay out of the board for 14 days unless impact worsens.
- Accessible list/kanban toggle and severity filters. Diagnostics remain separated from the main
  recommendation feed.
- Evidence opens in a SidePanel with session links, fix text, and Ack / Snooze 14d actions.
- Badge count on the rail for new insights. Static snapshots capture the insights payload.

## 13. Optimize (`/optimize`)

**Question:** _Close the loop: propose → apply → measure → verdict._

- Station board: Proposed → Applied → Measuring → Verdict.
- **Apply** / **Revert** per experiment (calls `experiment_apply` / `experiment_revert`).
- Copper dot on the rail when proposals are pending.
- See [Optimize loop](optimize.md).

## 13b. Guard (`/guard`)

**Question:** _Which instruction-file edits are associated with later session shifts?_

- Ledger reports event counts, association coverage, confounds, and git state.
- Events cover `AGENTS.md`, `CLAUDE.md`, and `.cursor/rules` with scrubbed diff summaries.
- Pre/post cost associations use anytime-valid intervals and say “associated with” /
  “observed after” — never causal. See [Guard](guard.md).

## 14. Live (`/live`)

**Question:** _What's happening right now?_

- SSE stream from `/api/live/events` follows the **Watch** topbar toggle (on by default in this
  browser until you turn it off). Static snapshots show an explicit unavailable empty state —
  no fake stream.
- Connection chip tracks connecting / connected / reconnecting / stale from named `heartbeat`
  frames (comment heartbeats still keep proxies warm). Auto-follow scrolls new events into view;
  Pause buffers up to 200 events.
- Dropped-event counter reflects server drop-oldest backpressure (queue size 64).
- Screen readers hear a polite summary of new activity, not every row.
- Links open Session Detail (active sessions use 2s polling live-tail). The sidebar shows coalesced
  `session_cost_tick` absolute totals with measured/estimated markers; screen readers hear a
  periodic summary rather than every tick. Session Detail Receipt uses versioned receipt v1
  (status, debt components, timeline); claim-to-evidence extraction stays unavailable.

## 15. Search (`/search`)

**Question:** _Find anything across sessions._

- Debounced, 500-character-bounded search uses the same parser and evaluator as Sessions. Results
  are server-paginated and grouped by trace; exact span links preserve `?span=` selection.
- Plain terms and quoted phrases search trace titles/projects and bounded span names, relative
  paths, and text. Snippets are inserted as text with React `<mark>` highlighting, never rendered
  as HTML. `j`/`k` moves through results and Enter opens the exact trace/span.
- Counted local facets are available for agent, outcome, date, relative file, and tool. Facet values
  are quoted and escaped before becoming a filter.
- This release uses an explicitly labeled bounded compatibility scan because FTS is unavailable;
  the UI never presents that degraded path as indexed full-text search.
- Successful recent queries stay only in this browser and have per-item delete and **Clear all**.
  **Copy privacy-safe filter link** omits the plain phrase, file, and agent filters.
- `claim:unsupported`, `corrected:true`, and `risk:high` are recognized but return honest
  unavailable feedback until their evidence tables/evaluators land. `verification:debt` and the
  retained `is:error` alias are working filters.
- Static snapshots include only the documented captured example queries; arbitrary or paginated
  search remains explicitly unsupported in snapshot mode.

## 16. Settings (`/settings`)

**Question:** _See what Cairn sees; change what it does._

Tabs (also via `?tab=`): Workspace, Appearance, Budget, Adapters, Data, MCP, Quality,
Privacy & Network, About.

- **Workspace** — name, root path, session/insight counts; bootstrap prompt.
- **Appearance** — OS / light / dark preference on this browser.
- **Budget** — live burn readout (`/api/analytics/budget`: month/week/day spend, linear and
  trailing-7d month-end projections, overrun date when warranted, agent/model shares) plus
  `budgets.monthly_usd|weekly_usd|daily_usd` via `config_set` (source shown).
- **Adapters** — source, stream count, parse-coverage canary, last ingest; **Rescan**.
- **Data** — Sync, export scrubbed bundle, rebuild views (Dialog + typed `rebuild` confirm with
  explicit scope). Retention/backup/restore/delete/reset are documented as unavailable until
  lifecycle APIs land — no dead buttons.
- **MCP** — install / print-only preview; last install path status in-session.
- **Quality** — `budgets.min_quality` plus human-label agreement readout.
- **Privacy & Network** — local-first / no-telemetry copy; opt-in reflector preview-consent boundary.
- **About** — version/health, changelog/license/docs links, `cairn doctor` / `cairn upgrade`.
- Token **gauge** in the rail footer when plan limits are configured.

## 17. Weekly recap (`/recap`)

**Question:** _What changed across this local seven-day recap window?_

- Rolling 7-day UTC window with explicit `period_start` / `period_end` / `period_kind`.
- Spend, avoidable spend, quality and cost-per-success trends, top causes, experiment verdicts,
  decayed rules, Guard events, best/worst sessions by cost (privacy-safe titles), and one
  recommended action when evidence exists.
- Reachable from Overview and the command palette; intentionally absent from the rail.
- Works in captured static snapshots (`/api/recap`). PNG share via `cairn recap --share`.
- Scheduling examples (cron / launchd / Task Scheduler) live in [recap.md](recap.md).

## Global chrome

- **Plaque topbar** — 24h / 7d / 30d / 90d and custom time range, Sync, Watch, and command
  palette (`⌘K`). A failed workspace request remains visible as **Local server disconnected**;
  cached counts are not presented as proof that the loopback server is healthy.
- **Command palette** — every working route, fuzzy session jump, theme and time-range preferences,
  and actions mirrored from the typed CLI/action registry. Static snapshots omit server-backed
  session search and mutations.
- **Keyboard** — `/` opens unified search; `?` opens the shortcut reference; `g` then
  `o`/`s`/`l`/`c`/`i` navigates to Overview/Sessions/Live/Context/Insights; `[` and `]` cycle
  preset ranges. These global keys do nothing while focus is in an input, textarea, or editable
  region. Page-local `j`/`k` behavior is listed in the shortcut overlay.
- **Detail breadcrumbs** — session detail and Session diff link back to Sessions and expose the current
  page with native breadcrumb semantics.
- **Collapsed rail** — icon links keep visible focus and accessible route names. The mobile dock
  exposes every current working route in a bounded, horizontally scrollable region.
- **Toasts** — undo for insight ack and other reversible actions.

Every button that mutates state calls `POST /api/actions/{name}` — the same handlers as the CLI.
