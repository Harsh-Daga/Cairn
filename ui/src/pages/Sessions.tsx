import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { fetchTraces, timeRangeDays } from "@/lib/api";
import { formatCost, formatRelative, formatTokens } from "@/lib/format";
import {
  DEFAULT_VIEW,
  deleteSavedView,
  loadSavedViews,
  paramsFromView,
  saveCurrentView,
  type SavedView,
} from "@/lib/savedViews";
import { useUiStore } from "@/state/ui";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";

const SOURCES = ["claude_code", "cursor", "codex"] as const;

export function SessionsPage() {
  const navigate = useNavigate();
  const timeRange = useUiStore((s) => s.timeRange);
  const [params, setParams] = useSearchParams();
  const [views, setViews] = useState<SavedView[]>(() => loadSavedViews());
  const [activeViewId, setActiveViewId] = useState("default");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [saveName, setSaveName] = useState("");
  const [compareIds, setCompareIds] = useState<string[]>([]);

  const days = Number(params.get("days")) || timeRangeDays(timeRange);
  const q = params.get("q") ?? undefined;
  const source = params.get("source") ?? undefined;
  const agent = params.get("agent") ?? undefined;
  const sort = params.get("sort") ?? "recent";

  const { data, isLoading, isError } = useQuery({
    queryKey: ["traces", days, q, source, agent],
    queryFn: () => fetchTraces({ days, q, source, limit: 100 }),
  });

  const traces = useMemo(() => {
    let rows = data?.traces ?? [];
    if (agent) {
      rows = rows.filter((t) => t.actor_id === agent || t.title?.includes(agent));
    }
    if (sort === "waste") {
      rows = [...rows].sort((a, b) => b.waste_tokens - a.waste_tokens);
    } else if (sort === "cost") {
      rows = [...rows].sort((a, b) => b.cost - a.cost);
    }
    return rows;
  }, [agent, data?.traces, sort]);

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
        setSelectedIndex((index) => Math.min(index + 1, traces.length - 1));
      } else if (event.key === "k") {
        event.preventDefault();
        setSelectedIndex((index) => Math.max(index - 1, 0));
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
      if (current.length >= 2) {
        const carry = current[1];
        return carry ? [carry, traceId] : [traceId];
      }
      return [...current, traceId];
    });
  };

  if (isLoading) {
    return (
      <PageShell title="Sessions" question="Find the session that matters.">
        <div className="card h-48 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError) {
    return (
      <PageShell title="Sessions" question="Find the session that matters.">
        <div className="card p-6 text-cinnabar">Failed to load sessions.</div>
      </PageShell>
    );
  }

  return (
    <PageShell title="Sessions" question="Find the session that matters.">
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
            compareIds.length === 2
              ? "border-copper text-copper hover:bg-copper/10"
              : "border-quartz-vein text-cinder"
          }`}
          disabled={compareIds.length !== 2}
          onClick={() => {
            const [a, b] = compareIds;
            if (!a || !b) return;
            navigate(`/sessions/diff?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
          }}
        >
          Compare selected ({compareIds.length}/2)
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
        {(["recent", "waste", "cost"] as const).map((s) => (
          <button
            key={s}
            type="button"
            className={`rounded-chip border px-2 py-1 font-mono text-[10px] ${
              sort === s ? "border-copper text-copper" : "border-quartz-vein text-cinder hover:text-bone"
            }`}
            onClick={() => setFilter("sort", s === "recent" ? null : s)}
          >
            {s}
          </button>
        ))}
        <span className="ml-2 font-mono text-[10px] uppercase tracking-wide text-cinder">Source</span>
        {SOURCES.map((s) => (
          <button
            key={s}
            type="button"
            className={`rounded-chip border px-2 py-1 font-mono text-[10px] ${
              source === s ? "border-copper text-copper" : "border-quartz-vein text-cinder hover:text-bone"
            }`}
            onClick={() => setFilter("source", source === s ? null : s)}
          >
            {s}
          </button>
        ))}
        {(source || sort !== "recent" || agent) ? (
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
            {traces.length} session{traces.length === 1 ? "" : "s"} · last {days} days · j/k navigate · Enter open
          </div>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-quartz-vein bg-slate font-mono text-[10px] uppercase tracking-wide text-cinder">
              <tr>
                <th className="px-4 py-3">Compare</th>
                <th className="px-4 py-3">Session</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3 text-right">Tokens</th>
                <th className="px-4 py-3 text-right">Waste</th>
                <th className="px-4 py-3 text-right">Cost</th>
                <th className="px-4 py-3 text-right">When</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((trace, index) => {
                const estimated = trace.cost_source === "absent" || trace.cost_source === "estimated";
                const selected = index === selectedIndex;
                return (
                  <tr
                    key={trace.trace_id}
                    data-trace-row
                    className={`border-b border-quartz-vein/50 hover:bg-granite/20 ${
                      selected ? "bg-copper/10 ring-1 ring-inset ring-copper/30" : ""
                    }`}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={compareIds.includes(trace.trace_id)}
                        onChange={() => toggleCompare(trace.trace_id)}
                        aria-label={`Select ${trace.trace_id} for compare`}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        to={`/sessions/${trace.trace_id}`}
                        className="font-medium text-bone hover:text-copper"
                      >
                        {trace.title ?? trace.trace_id.slice(0, 12)}
                      </Link>
                      <p className="mt-0.5 font-mono text-[10px] text-cinder">{trace.trace_id}</p>
                    </td>
                    <td className="px-4 py-3">
                      <Chip label={trace.source} tone="patina" />
                    </td>
                    <td className={`px-4 py-3 text-right font-mono text-xs ${estimated ? "estimated-chip" : ""}`}>
                      {formatTokens(trace.input_tokens + trace.output_tokens)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-ochre">
                      {trace.waste_tokens > 0 ? formatTokens(trace.waste_tokens) : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">
                      {formatCost(trace.cost)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-[10px] text-cinder">
                      {trace.started_at ? formatRelative(trace.started_at) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </PageShell>
  );
}
