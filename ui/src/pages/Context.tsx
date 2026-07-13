import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchRegions, fetchUsage, fetchWaste, timeRangeDays } from "@/lib/api";
import { formatTokens } from "@/lib/format";
import { useUiStore } from "@/state/ui";
import type { UsageSeriesRow } from "@/lib/types";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { HorizontalBars, StackedArea } from "@/components/charts";

const REGION_LABELS: Record<string, string> = {
  system: "System prompt",
  tool_schema: "Tool schemas",
  tool_result: "Tool results",
  retrieved: "Retrieved context",
  user: "User messages",
  history: "Conversation history",
};

export function ContextPage() {
  const timeRange = useUiStore((s) => s.timeRange);
  const days = timeRangeDays(timeRange);

  const regionsQ = useQuery({
    queryKey: ["regions", days],
    queryFn: () => fetchRegions(days),
  });
  const wasteQ = useQuery({
    queryKey: ["waste", days],
    queryFn: () => fetchWaste(days),
  });
  const usageQ = useQuery({
    queryKey: ["usage", days],
    queryFn: () => fetchUsage(days),
  });

  if (regionsQ.isLoading || wasteQ.isLoading) {
    return (
      <PageShell title="Context" question="See what filled the context window, what was re-billed, and where to cut waste.">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (regionsQ.isError || wasteQ.isError) {
    return (
      <PageShell title="Context" question="See what filled the context window, what was re-billed, and where to cut waste.">
        <ErrorCard />
      </PageShell>
    );
  }

  const regions = regionsQ.data?.regions ?? [];
  const waste = wasteQ.data;
  const usageSeries = usageQ.data?.series ?? [];
  const totalTokens = regions.reduce((sum, r) => sum + Number(r.tokens), 0);
  const toolResultTokens =
    regions.find((r) => r.region === "tool_result")?.tokens ?? 0;
  const toolPct = totalTokens > 0 ? Math.round((toolResultTokens / totalTokens) * 100) : 0;

  if (regions.length === 0) {
    return (
      <PageShell title="Context" question="See what filled the context window, what was re-billed, and where to cut waste.">
        <EmptyCard
          title="No region data yet"
          detail="Sessions from this source don't expose context internals — check data notes after sync."
        />
      </PageShell>
    );
  }

  const tokenComposition = usageSeries.map((r: UsageSeriesRow) => ({
    day: r.key.slice(5) || r.key,
    input: Number(r.input_tokens),
    output: Number(r.output_tokens),
  }));

  const hotspotRows =
    regions.length > 0
      ? regions
          .slice()
          .sort((a, b) => Number(b.spans) - Number(a.spans))
          .slice(0, 8)
          .map((r) => ({
            path: REGION_LABELS[r.region] ?? r.region,
            spans: Number(r.spans),
            tokens: Number(r.tokens),
          }))
      : (waste?.categories ?? []).slice(0, 8).map((c) => ({
          path: c.category.replace(/_/g, " "),
          spans: Number(c.events ?? 0),
          tokens: Number(c.tokens),
        }));

  return (
    <PageShell title="Context" question="See what filled the context window, what was re-billed, and where to cut waste.">
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="card p-4">
            <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">Tool results share</p>
            <p className="mt-1 font-display text-2xl text-bone">{toolPct}%</p>
            <p className="mt-1 text-sm text-cinder">Your context is {toolPct}% tool results on average.</p>
          </div>
          <div className="card p-4">
            <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">Avoidable context</p>
            <p className="mt-1 font-display text-2xl text-bone">
              {formatTokens(waste?.total_waste_tokens ?? 0)}
            </p>
            <p className="mt-1 text-sm text-cinder">Tokens flagged as waste this period.</p>
          </div>
          <div className="card p-4">
            <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">Total context</p>
            <p className="mt-1 font-display text-2xl text-bone">{formatTokens(totalTokens)}</p>
            <Link to="/sessions" className="mt-1 inline-block text-sm text-copper hover:underline">
              View sessions →
            </Link>
          </div>
        </div>

        <ChartFrame
          title="Context composition"
          subtitle={
            usageSeries.length > 1 ? "Daily token mix (input vs output)" : "Tokens by region"
          }
        >
          {usageSeries.length > 1 ? (
            <StackedArea
              data={tokenComposition}
              keys={["input", "output"]}
              xKey="day"
              width={640}
              height={200}
            />
          ) : (
            <HorizontalBars
              items={regions.map((r) => ({
                label: REGION_LABELS[r.region] ?? r.region,
                value: Number(r.tokens),
              }))}
              width={480}
            />
          )}
        </ChartFrame>

        <ChartFrame title="Hotspots" subtitle="Top regions or waste categories by span count">
          {hotspotRows.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="font-mono text-[10px] uppercase tracking-wide text-cinder">
                  <tr>
                    <th className="px-2 py-2">Path / category</th>
                    <th className="px-2 py-2 text-right">Spans</th>
                    <th className="px-2 py-2 text-right">Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {hotspotRows.map((row) => (
                    <tr key={row.path} className="border-t border-quartz-vein/50">
                      <td className="px-2 py-2 font-mono text-xs text-bone">{row.path}</td>
                      <td className="px-2 py-2 text-right font-mono text-xs text-cinder">
                        {row.spans.toLocaleString()}
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-xs text-bone">
                        {formatTokens(row.tokens)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-cinder">No hotspot data in this window.</p>
          )}
        </ChartFrame>

        <ChartFrame title="Waste ledger" subtitle="Detected categories; uncategorized estimates remain explicit">
          {(waste?.categories ?? []).length > 0 ? (
            <HorizontalBars
              items={(waste?.categories ?? []).map((c) => ({
                label: c.category.replace(/_/g, " "),
                value: Number(c.tokens),
              }))}
              width={480}
            />
          ) : (
            <p className="text-sm text-cinder">No waste categories recorded yet.</p>
          )}
          {waste && waste.total_waste_tokens > 0 ? (
            <p className="mt-4 text-sm text-cinder">
              Waste is a subset of input tokens, not an additional token charge. Cost impact uses
              each session&apos;s measured or estimated model price on Overview.
            </p>
          ) : null}
        </ChartFrame>
      </div>
    </PageShell>
  );
}
