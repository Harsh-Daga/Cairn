import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { fetchTraceDiff } from "@/lib/api";
import { formatCost, formatTokens } from "@/lib/format";
import { PageShell } from "@/components/common/PageShell";

function formatDelta(value: number, digits = 0): string {
  if (value > 0) return `+${value.toFixed(digits)}`;
  return value.toFixed(digits);
}

export function SessionDiffPage() {
  const [params] = useSearchParams();
  const traceIdA = params.get("a");
  const traceIdB = params.get("b");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["trace-diff", traceIdA, traceIdB],
    queryFn: () => fetchTraceDiff(traceIdA!, traceIdB!),
    enabled: Boolean(traceIdA && traceIdB),
  });

  if (!traceIdA || !traceIdB) {
    return (
      <PageShell title="Session diff" question="Compare two runs turn by turn to explain changes in cost, waste, and quality.">
        <div className="card p-6 text-cinnabar">Select two sessions first from the Sessions page.</div>
      </PageShell>
    );
  }

  if (isLoading) {
    return (
      <PageShell title="Session diff" question="Compare two runs turn by turn to explain changes in cost, waste, and quality.">
        <div className="card h-64 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell title="Session diff" question="Compare two runs turn by turn to explain changes in cost, waste, and quality.">
        <div className="card p-6 text-cinnabar">Failed to load diff payload.</div>
      </PageShell>
    );
  }

  return (
    <PageShell title="Session diff" question="Compare two runs turn by turn to explain changes in cost, waste, and quality.">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Link to="/sessions" className="font-mono text-xs text-copper hover:underline">
          ← Sessions
        </Link>
        <span className="font-mono text-[11px] text-cinder">A: {data.a.trace_id}</span>
        <span className="font-mono text-[11px] text-cinder">B: {data.b.trace_id}</span>
      </div>

      <div className="mb-4 grid gap-3 md:grid-cols-3">
        <div className="card p-3">
          <div className="font-mono text-[10px] uppercase tracking-wide text-cinder">Cost delta</div>
          <div className="mt-1 text-lg text-bone">
            {formatCost(data.summary.cost_a)} → {formatCost(data.summary.cost_b)}
          </div>
          <div className="font-mono text-xs text-copper">{formatDelta(data.summary.delta_cost, 4)}</div>
        </div>
        <div className="card p-3">
          <div className="font-mono text-[10px] uppercase tracking-wide text-cinder">Waste delta</div>
          <div className="mt-1 text-lg text-bone">
            {formatTokens(data.summary.waste_a)} → {formatTokens(data.summary.waste_b)}
          </div>
          <div className="font-mono text-xs text-copper">
            {formatDelta(data.summary.delta_waste_tokens)}
          </div>
        </div>
        <div className="card p-3">
          <div className="font-mono text-[10px] uppercase tracking-wide text-cinder">Quality delta</div>
          <div className="mt-1 text-lg text-bone">
            {(data.summary.quality_a * 100).toFixed(0)}% → {(data.summary.quality_b * 100).toFixed(0)}%
          </div>
          <div className="font-mono text-xs text-copper">
            {formatDelta(data.summary.delta_quality * 100, 1)} pts
          </div>
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-quartz-vein bg-slate font-mono text-[10px] uppercase tracking-wide text-cinder">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Turn</th>
              <th className="px-3 py-2 text-right">Δ tokens</th>
              <th className="px-3 py-2 text-right">Δ waste</th>
              <th className="px-3 py-2 text-right">Δ quality</th>
            </tr>
          </thead>
          <tbody>
            {data.turns.map((turn) => {
              const labelA = turn.a ? `${turn.a.kind}:${turn.a.name ?? "(unnamed)"}` : "—";
              const labelB = turn.b ? `${turn.b.kind}:${turn.b.name ?? "(unnamed)"}` : "—";
              return (
                <tr key={`${turn.index}-${turn.op}`} className="border-b border-quartz-vein/50">
                  <td className="px-3 py-2 font-mono text-xs text-cinder">{turn.index}</td>
                  <td className="px-3 py-2">
                    <div className="font-mono text-[10px] uppercase text-cinder">{turn.op}</div>
                    <div className="text-xs text-bone">{labelA}</div>
                    <div className="text-xs text-cinder">→ {labelB}</div>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {formatDelta(turn.delta_tokens)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {formatDelta(turn.delta_waste_tokens)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {formatDelta(turn.delta_quality, 2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </PageShell>
  );
}
