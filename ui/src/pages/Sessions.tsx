import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { fetchTraces, timeRangeDays } from "@/lib/api";
import { formatCost, formatRelative, formatTokens } from "@/lib/format";
import { useUiStore } from "@/state/ui";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";

const SOURCES = ["claude_code", "cursor", "codex"] as const;

export function SessionsPage() {
  const timeRange = useUiStore((s) => s.timeRange);
  const [params, setParams] = useSearchParams();
  const days = Number(params.get("days")) || timeRangeDays(timeRange);
  const q = params.get("q") ?? undefined;
  const source = params.get("source") ?? undefined;
  const agent = params.get("agent") ?? undefined;
  const sort = params.get("sort") ?? "recent";

  const { data, isLoading, isError } = useQuery({
    queryKey: ["traces", days, q, source, agent],
    queryFn: () => fetchTraces({ days, q, source, limit: 100 }),
  });

  let traces = data?.traces ?? [];
  if (agent) {
    traces = traces.filter((t) => t.actor_id === agent || t.title?.includes(agent));
  }
  if (sort === "waste") {
    traces = [...traces].sort((a, b) => b.waste_tokens - a.waste_tokens);
  } else if (sort === "cost") {
    traces = [...traces].sort((a, b) => b.cost - a.cost);
  }

  const setFilter = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
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
            onClick={() => setParams(new URLSearchParams())}
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
            {traces.length} session{traces.length === 1 ? "" : "s"} · last {days} days
          </div>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-quartz-vein bg-slate font-mono text-[10px] uppercase tracking-wide text-cinder">
              <tr>
                <th className="px-4 py-3">Session</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3 text-right">Tokens</th>
                <th className="px-4 py-3 text-right">Waste</th>
                <th className="px-4 py-3 text-right">Cost</th>
                <th className="px-4 py-3 text-right">When</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((trace) => {
                const estimated = trace.cost_source === "absent" || trace.cost_source === "estimated";
                return (
                  <tr
                    key={trace.trace_id}
                    className="border-b border-quartz-vein/50 hover:bg-granite/20"
                  >
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
