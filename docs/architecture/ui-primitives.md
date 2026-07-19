# UI primitive boundaries

Reusable interaction and presentation contracts live in `ui/src/components/ui/`. Pages compose
these primitives with domain data; they should not copy modal focus code, invent metric semantics,
or build ad hoc pagination controls.

## Ownership

| Module | Contract | 1.2 adoption |
| --- | --- | --- |
| `Card` / `Stat` | `Stat` with `detail` is the analyze-page KPI card; bare `Stat` supports prior-period delta; standalone `Card` shell is available | **`Stat` adopted**; `Card` mostly unused outside tests |
| `Feedback` | Geometry-aware loading, named empty state, announced inline failure/retry | Partial via `DataViews` |
| `Indicators` | Severity badges, visibly distinct estimates, textual confidence intervals | `EstimateBadge` adopted; `Badge`/`ConfidenceInterval` available |
| `Actions` | Explicit clipboard action and router-aware breadcrumbs | Adopted |
| `Controls` | Pressed-state segmented controls and labeled field errors | Used by `TimeRangePicker` |
| `Overlays` | Modal `Dialog`/`SidePanel` focus, Escape, backdrop, restoration | Adopted |
| `DataTable` | Table semantics, sort, bounded server pages, optional virtualization | **Adopted on Tools** (normalized tools + coverage); Sessions keeps a purpose-built virtualized table |
| `TimeRangePicker` | Presets and validated custom local datetime/IANA-timezone input | Adopted |
| `ErrorBoundary` | Local render containment with no telemetry or private error disclosure | Adopted |

`Tooltip` / `Popover` remain available but unused in production pages; do not treat them as
required surface for 1.2.

`ui/src/hooks/useModalFocus.ts` is the single modal trap/restore implementation. A modal must use
that hook directly or use `Dialog`/`SidePanel`; a non-modal popover must close on outside
interaction and Escape without making background content inert.

Overview hero KPIs (`Kpi`) stay page-local: they encode sparkline + prior-period states that the
shared `Stat` card grammar does not attempt to replace.

## Data table constraints

The backend remains responsible for total counts, filters, and bounded pages. `DataTable` never
materializes an unbounded result set. Pages pass the current page and page count, then handle
`onPageChange`. Tools uses client-bounded analyzer pages (already capped server-side). Sessions
keeps a purpose-built virtualized table with the same keyboard contract (`j`/`k`, Enter/Space).

## Metric and status grammar

Use `MetricHelp` only when definition, calculation, source, or limitations are not obvious.
Estimated values use text plus a dashed marker (`EstimateBadge` or `Stat estimated`). Confidence
intervals expose the estimate and both bounds as one accessible label. Severity badges always
retain visible words; color is supplemental.

All primitives must have focused behavior tests. Interactive primitives also require axe coverage
and at least one seeded browser journey when integrated. Do not weaken the all-route axe gate to
admit a new primitive.

## Chart contract

Every data visualization is composed inside `components/charts/ChartFrame`. The frame requires a
plain-language conclusion sentence and may expose the exact plotted values in a native table.
Charts that encode values visually must provide that table; a nearby textual value is sufficient
for a decorative sparkline that repeats a metric. The visual SVG is supplementary and must retain
an accessible name.

Public number, currency, percentage, and date labels use `lib/format.ts` so chart summaries,
tooltips, tables, and adjacent metrics agree. Units belong in the column or series label. A
stacked-area plot exposes pointer inspection plus focus and Left/Right/Home/End inspection with a
polite value announcement. Adding pointer-only chart state is not permitted.

Stacked charts display at most seven series. The shared renderer retains the first six series and
deterministically sums the remainder into `other`; callers must keep the same ordering in their
table alternative. SVG definitions use per-instance identifiers so multiple charts cannot resolve
another chart's gradients, patterns, or filters.
