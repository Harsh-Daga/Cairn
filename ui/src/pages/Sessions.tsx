import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { fetchTraces } from "@/lib/api";
import {
  formatCost,
  formatDecimal,
  formatDuration,
  formatRelative,
  formatTokens,
} from "@/lib/format";
import {
  DEFAULT_VIEW,
  deleteSavedView,
  loadSavedViews,
  paramsFromView,
  saveCurrentView,
  type SavedView,
} from "@/lib/savedViews";
import { useSelectedTimeRange } from "@/hooks/useSelectedTimeRange";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import { timeRangeLabel } from "@/lib/timeRange";
import { FilterQuery } from "@/components/common/FilterQuery";
import { Sparkline } from "@/components/charts";
import { privacySafeFilterUrl } from "@/lib/filterPrivacy";

const SOURCES = ["claude_code", "cursor", "codex", "cline"] as const;
const PAGE_SIZE = 50;

export function SessionsPage() {
  const navigate = useNavigate();
  const { range, rangeKey } = useSelectedTimeRange();
  const rangeLabel = timeRangeLabel(range);
  const [params, setParams] = useSearchParams();
  const [views, setViews] = useState<SavedView[]>(() => loadSavedViews());
  const [activeViewId, setActiveViewId] = useState("default");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [saveName, setSaveName] = useState("");
  const [compareIds, setCompareIds] = useState<string[]>(() => {
    const selected = params.get("selected");
    return selected ? [selected] : [];
  });
  const [filterDraft, setFilterDraft] = useState(() => params.get("q") ?? "");
  const [showMultiSummary, setShowMultiSummary] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const q = params.get("q") ?? undefined;
  const source = params.get("source") ?? undefined;
  const agent = params.get("agent") ?? undefined;
  const sort = params.get("sort") ?? "recent";
  const page = Math.max(1, Number(params.get("page")) || 1);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["traces", rangeKey, q, source, agent, sort, page],
    queryFn: () =>
      fetchTraces({
        range,
        q,
        source,
        agent,
        sort: sort as "recent" | "waste" | "cost" | "duration" | "tokens" | "quality",
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      }),
  });

  const traces = useMemo(() => data?.traces ?? [], [data?.traces]);
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const virtualizer = useVirtualizer({
    count: traces.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 88,
    overscan: 6,
  });
  const selectedTraces = traces.filter((trace) => compareIds.includes(trace.trace_id));

  useEffect(() => {
    setFilterDraft(params.get("q") ?? "");
  }, [params]);

  useEffect(() => {
    setSelectedIndex((index) => Math.min(index, Math.max(traces.length - 1, 0)));
  }, [traces.length]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA")
      ) {
        return;
      }
      if (traces.length === 0) return;
      if (event.key === "j") {
        event.preventDefault();
        setSelectedIndex((index) => {
          const next = Math.min(index + 1, traces.length - 1);
          window.requestAnimationFrame(() => {
            document.querySelector<HTMLElement>(`[data-trace-index="${next}"]`)?.focus();
          });
          return next;
        });
      } else if (event.key === "k") {
        event.preventDefault();
        setSelectedIndex((index) => {
          const next = Math.max(index - 1, 0);
          window.requestAnimationFrame(() => {
            document.querySelector<HTMLElement>(`[data-trace-index="${next}"]`)?.focus();
          });
          return next;
        });
      } else if (event.key === "Enter") {
        const trace = traces[selectedIndex];
        if (trace) {
          event.preventDefault();
          navigate(`/sessions/${trace.trace_id}`);
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate, selectedIndex, traces]);

  const setFilter = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page");
    setParams(next);
    setActiveViewId("");
  };

  const applyView = (view: SavedView) => {
    setActiveViewId(view.id);
    setParams(paramsFromView(view));
  };

  const handleSaveView = () => {
    const next = saveCurrentView(saveName, params);
    setViews(next);
    setSaveName("");
    const saved = next[next.length - 1];
    if (saved) setActiveViewId(saved.id);
  };

  const handleDeleteView = (id: string) => {
    const next = deleteSavedView(id);
    setViews(next);
    if (activeViewId === id) {
      applyView(DEFAULT_VIEW);
    }
  };

  const toggleCompare = (traceId: string) => {
    setCompareIds((current) => {
      if (current.includes(traceId)) return current.filter((id) => id !== traceId);
      if (current.length >= 20) return current;
      return [...current, traceId];
    });
    setShowMultiSummary(false);
  };

  if (isLoading) {
    return (
      <PageShell
        title="Sessions"
        question="Filter, compare, and investigate the runs behind your workspace signals."
      >
        <div className="card h-48 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError) {
    return (
      <PageShell
        title="Sessions"
        question="Filter, compare, and investigate the runs behind your workspace signals."
      >
        <div className="card p-6 text-cinnabar">Failed to load sessions.</div>
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Sessions"
      question="Filter, compare, and investigate the runs behind your workspace signals."
    >
      <div className="card mb-4 p-4">
        <FilterQuery
          label="Session filter"
          value={filterDraft}
          onChange={setFilterDraft}
          onSubmit={(value) => setFilter("q", value || null)}
          tokens={data?.filter_tokens}
          errors={data?.filter_errors}
          placeholder='agent:codex cost:>1 outcome:fail file:"src/app.py"'
        />
        <button
          type="button"
          className="mt-3 text-xs text-copper hover:underline"
          onClick={async () => {
            await navigator.clipboard.writeText(
              privacySafeFilterUrl(window.location.href, data?.filter_tokens ?? []),
            );
            setLinkCopied(true);
          }}
        >
          {linkCopied ? "Privacy-safe link copied" : "Copy privacy-safe filter link"}
        </button>
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {views.map((view) => (
          <div key={view.id} className="flex items-center gap-1">
            <button
              type="button"
              className={`rounded-chip border px-2 py-1 font-mono text-[10px] ${
                activeViewId === view.id
                  ? "border-copper text-copper"
                  : "border-quartz-vein text-cinder hover:text-bone"
              }`}
              onClick={() => applyView(view)}
              aria-pressed={activeViewId === view.id}
            >
              {view.name}
            </button>
            {!view.pinned ? (
              <button
                type="button"
                className="font-mono text-[10px] text-cinder hover:text-cinnabar"
                aria-label={`Delete view ${view.name}`}
                onClick={() => handleDeleteView(view.id)}
              >
                ✕
              </button>
            ) : null}
          </div>
        ))}
        <input
          type="text"
          value={saveName}
          onChange={(event) => setSaveName(event.target.value)}
          placeholder="Save view as…"
          className="rounded-sm border border-quartz-vein bg-slate px-2 py-1 font-mono text-[10px] text-bone"
        />
        <button
          type="button"
          className="rounded-chip border border-quartz-vein px-2 py-1 font-mono text-[10px] text-cinder hover:text-bone"
          onClick={handleSaveView}
        >
          Save view
        </button>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          className={`rounded-chip border px-2 py-1 font-mono text-[10px] ${
            compareIds.length >= 2
              ? "border-copper text-copper hover:bg-copper/10"
              : "border-quartz-vein text-cinder"
          }`}
          disabled={compareIds.length < 2}
          onClick={() => {
            if (compareIds.length >= 3) {
              setShowMultiSummary(true);
              return;
            }
            const [a, b] = compareIds;
            if (!a || !b) return;
            navigate(`/sessions/diff?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
          }}
        >
          {compareIds.length >= 3 ? "Summarize selected" : "Compare selected"} ({compareIds.length})
        </button>
        {compareIds.length > 0 ? (
          <button
            type="button"
            className="rounded-chip border border-quartz-vein px-2 py-1 font-mono text-[10px] text-cinder hover:text-bone"
            onClick={() => setCompareIds([])}
          >
            Clear selection
          </button>
        ) : null}
        <span className="font-mono text-[10px] uppercase tracking-wide text-cinder">Sort</span>
        {(["recent", "waste", "cost", "duration", "tokens", "quality"] as const).map((s) => (
          <button
            key={s}
            type="button"
            className={`rounded-chip border px-2 py-1 font-mono text-[10px] ${
              sort === s
                ? "border-copper text-copper"
                : "border-quartz-vein text-cinder hover:text-bone"
            }`}
            onClick={() => setFilter("sort", s === "recent" ? null : s)}
            aria-pressed={sort === s}
          >
            {s}
          </button>
        ))}
        <span className="ml-2 font-mono text-[10px] uppercase tracking-wide text-cinder">
          Source
        </span>
        {SOURCES.map((s) => (
          <button
            key={s}
            type="button"
            className={`rounded-chip border px-2 py-1 font-mono text-[10px] ${
              source === s
                ? "border-copper text-copper"
                : "border-quartz-vein text-cinder hover:text-bone"
            }`}
            onClick={() => setFilter("source", source === s ? null : s)}
            aria-pressed={source === s}
          >
            {s}
          </button>
        ))}
        {q || source || sort !== "recent" || agent ? (
          <button
            type="button"
            className="font-mono text-[10px] text-copper hover:underline"
            onClick={() => {
              setParams(new URLSearchParams());
              setActiveViewId("default");
            }}
          >
            Clear filters
          </button>
        ) : null}
      </div>

      {showMultiSummary && selectedTraces.length >= 3 ? (
        <section className="card mb-4 p-4" aria-label="Selected session summary">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="page-kicker">Multi-session summary</p>
              <h2 className="font-display text-base text-bone">
                {selectedTraces.length} selected sessions
              </h2>
            </div>
            <button
              type="button"
              className="text-xs text-cinder hover:text-bone"
              onClick={() => setShowMultiSummary(false)}
            >
              Close
            </button>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <SummaryMetric
              label="Spend"
              value={formatCost(selectedTraces.reduce((sum, trace) => sum + Number(trace.cost), 0))}
            />
            <SummaryMetric
              label="Tokens"
              value={formatTokens(
                selectedTraces.reduce(
                  (sum, trace) => sum + trace.input_tokens + trace.output_tokens,
                  0,
                ),
              )}
            />
            <SummaryMetric
              label="Waste"
              value={formatTokens(
                selectedTraces.reduce((sum, trace) => sum + trace.waste_tokens, 0),
              )}
            />
            <SummaryMetric
              label="Quality mean"
              value={
                selectedTraces.some((trace) => trace.quality_score != null)
                  ? formatDecimal(
                      selectedTraces.reduce(
                        (sum, trace) => sum + Number(trace.quality_score ?? 0),
                        0,
                      ) / selectedTraces.filter((trace) => trace.quality_score != null).length,
                    )
                  : "Unavailable"
              }
            />
            <SummaryMetric
              label="Verified"
              value={`${selectedTraces.filter((trace) => trace.verification_state === "verified").length}/${selectedTraces.length}`}
            />
          </div>
          <p className="mt-3 text-xs text-cinder">
            Descriptive totals only. This summary does not assert comparability or causal
            differences across the selected sessions.
          </p>
        </section>
      ) : null}

      {traces.length === 0 ? (
        <div className="card empty-state">
          <h2>No sessions in range</h2>
          <p className="mt-2 text-sm">
            {source || agent
              ? "No sessions match the current filters — try clearing filters or widening the time range."
              : "Run cairn sync to ingest agent logs."}
          </p>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <div className="border-b border-quartz-vein px-4 py-2 font-mono text-[10px] text-cinder">
            {total} session{total === 1 ? "" : "s"} · page {page} of {totalPages} · {rangeLabel} ·
            {virtualizer.getVirtualItems().length} visible rows · j/k navigate · Enter open
          </div>
          <div
            ref={scrollRef}
            className="max-h-[640px] overflow-auto"
            role="table"
            aria-label={`Sessions for ${rangeLabel}, sorted by ${sort}`}
            aria-rowcount={traces.length + 1}
          >
            <div
              role="row"
              className="sticky top-0 z-10 grid min-w-[1180px] grid-cols-[44px_minmax(260px,2fr)_130px_120px_110px_90px_90px_110px_120px] border-b border-quartz-vein bg-slate font-mono text-[10px] uppercase tracking-wide text-cinder"
            >
              {[
                "Select",
                "Session",
                "Agent / source",
                "Start / duration",
                "Tokens",
                "Cost",
                "Waste",
                "Quality",
                "Outcome / verification",
              ].map((label) => (
                <div key={label} role="columnheader" className="px-3 py-3">
                  {label}
                </div>
              ))}
            </div>
            <div
              role="rowgroup"
              className="relative min-w-[1180px]"
              style={{ height: `${virtualizer.getTotalSize()}px` }}
            >
              {virtualizer.getVirtualItems().map((virtualRow) => {
                const trace = traces[virtualRow.index];
                if (!trace) return null;
                const selected = virtualRow.index === selectedIndex;
                const estimated =
                  trace.cost_source === "absent" || trace.cost_source === "estimated";
                return (
                  <div
                    key={trace.trace_id}
                    ref={virtualizer.measureElement}
                    data-index={virtualRow.index}
                    data-trace-row
                    data-trace-index={virtualRow.index}
                    role="row"
                    tabIndex={selected ? 0 : -1}
                    aria-selected={selected}
                    onFocus={() => setSelectedIndex(virtualRow.index)}
                    className={`absolute left-0 top-0 grid w-full min-w-[1180px] grid-cols-[44px_minmax(260px,2fr)_130px_120px_110px_90px_90px_110px_120px] border-b border-quartz-vein/50 hover:bg-granite/20 ${
                      selected ? "bg-copper/10 ring-1 ring-inset ring-copper/30" : "bg-anthracite"
                    }`}
                    style={{ transform: `translateY(${virtualRow.start}px)` }}
                  >
                    <div role="cell" className="px-3 py-3">
                      <input
                        type="checkbox"
                        checked={compareIds.includes(trace.trace_id)}
                        onChange={() => toggleCompare(trace.trace_id)}
                        aria-label={`Select ${trace.trace_id} for compare`}
                      />
                    </div>
                    <div role="cell" className="min-w-0 px-3 py-3">
                      <Link
                        to={`/sessions/${trace.trace_id}`}
                        className="font-medium text-bone hover:text-copper"
                      >
                        {trace.title ?? trace.trace_id.slice(0, 12)}
                      </Link>
                      <p className="mt-0.5 truncate font-mono text-[10px] text-cinder">
                        {trace.trace_id}
                      </p>
                      <details className="mt-2 text-xs text-cinder">
                        <summary className="cursor-pointer text-copper">Preview</summary>
                        <p className="mt-2 line-clamp-3 text-bone">
                          {trace.first_user_request ?? "First user request unavailable."}
                        </p>
                        <p className="mt-1 font-mono text-[10px] text-ash">
                          Files: {trace.top_files.length > 0 ? trace.top_files.join(", ") : "none"}
                        </p>
                        <p className="mt-1 font-mono text-[10px] text-ash">
                          Data: {trace.data_quality_state}
                        </p>
                      </details>
                    </div>
                    <div role="cell" className="px-3 py-3">
                      <p className="truncate text-xs text-bone">{trace.actor_id ?? trace.source}</p>
                      <p className="mt-1 truncate font-mono text-[10px] text-cinder">
                        {trace.actor_id ? trace.source : (trace.model ?? "model unknown")}
                      </p>
                    </div>
                    <div role="cell" className="px-3 py-3 font-mono text-[10px] text-cinder">
                      <p>{trace.started_at ? formatRelative(trace.started_at) : "—"}</p>
                      <p className="mt-1">{formatDuration(trace.duration_ms)}</p>
                    </div>
                    <div
                      role="cell"
                      className={`px-3 py-3 font-mono text-xs ${estimated ? "estimated-chip" : ""}`}
                    >
                      <p>{formatTokens(trace.input_tokens + trace.output_tokens)}</p>
                      {trace.token_flow.length > 1 ? (
                        <Sparkline data={trace.token_flow} width={76} height={22} />
                      ) : (
                        <p className="mt-1 text-[9px] text-ash">flow unavailable</p>
                      )}
                    </div>
                    <div role="cell" className="px-3 py-3 font-mono text-xs">
                      {formatCost(trace.cost)}
                    </div>
                    <div role="cell" className="px-3 py-3 font-mono text-xs text-ochre">
                      {trace.waste_tokens > 0 ? formatTokens(trace.waste_tokens) : "—"}
                    </div>
                    <div role="cell" className="px-3 py-3">
                      <p className="font-mono text-xs text-bone">
                        {trace.quality_score == null ? "—" : formatDecimal(trace.quality_score)}
                      </p>
                      <p className="mt-1 font-mono text-[9px] text-ash">
                        {trace.data_quality_state}
                      </p>
                    </div>
                    <div role="cell" className="px-3 py-3">
                      <p className="truncate text-xs text-bone">
                        {trace.outcome_label ?? trace.status}
                      </p>
                      <span className="mt-1 inline-flex">
                        <Chip
                          label={trace.verification_state}
                          tone={
                            trace.verification_state === "failed" ||
                            trace.verification_state === "debt"
                              ? "cinnabar"
                              : trace.verification_state === "verified"
                                ? "patina"
                                : "estimated"
                          }
                        />
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <p className="sr-only" aria-live="polite">
            Selected session {selectedIndex + 1} of {traces.length}
          </p>
        </div>
      )}
      {totalPages > 1 ? (
        <div className="mt-4 flex items-center justify-between">
          <button
            type="button"
            disabled={page <= 1}
            className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone disabled:opacity-40"
            onClick={() => setFilter("page", String(page - 1))}
          >
            ← Previous
          </button>
          <span className="font-mono text-xs text-cinder">
            {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone disabled:opacity-40"
            onClick={() => setFilter("page", String(page + 1))}
          >
            Next →
          </button>
        </div>
      ) : null}
    </PageShell>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-sm border border-quartz-vein p-3">
      <p className="font-mono text-[9px] uppercase tracking-wide text-cinder">{label}</p>
      <p className="mt-2 font-display text-lg text-bone">{value}</p>
    </div>
  );
}
