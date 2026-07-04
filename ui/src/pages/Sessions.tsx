import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { fetchTraces, timeRangeDays } from "@/lib/api";
import { formatCost, formatRelative, formatTokens } from "@/lib/format";
import { useUiStore } from "@/state/ui";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";

export function SessionsPage() {
  const timeRange = useUiStore((s) => s.timeRange);
  const [params] = useSearchParams();
  const days = Number(params.get("days")) || timeRangeDays(timeRange);
  const q = params.get("q") ?? undefined;
  const source = params.get("source") ?? undefined;

  const { data, isLoading, isError } = useQuery({
    queryKey: ["traces", days, q, source],
    queryFn: () => fetchTraces({ days, q, source, limit: 100 }),
  });

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

  const traces = data?.traces ?? [];

  return (
    <PageShell title="Sessions" question="Find the session that matters.">
      {traces.length === 0 ? (
        <div className="card empty-state">
          <h2>No sessions in range</h2>
          <p className="mt-2 text-sm">Run cairn sync to ingest agent logs.</p>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-quartz-vein bg-slate font-mono text-[10px] uppercase tracking-wide text-cinder">
              <tr>
                <th className="px-4 py-3">Session</th>
                <th className="px-4 py-3">Source</th>
                <th className="px-4 py-3 text-right">Tokens</th>
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
