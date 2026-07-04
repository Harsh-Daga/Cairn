import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchRegions, fetchWaste, timeRangeDays } from "@/lib/api";
import { formatCost, formatTokens } from "@/lib/format";
import { useUiStore } from "@/state/ui";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame } from "@/components/common/Chip";
import { EmptyCard, ErrorCard, HorizontalBars } from "@/components/common/DataViews";

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

  if (regionsQ.isLoading || wasteQ.isLoading) {
    return (
      <PageShell title="Context" question="Where does every token go, and what's re-billed?">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (regionsQ.isError || wasteQ.isError) {
    return (
      <PageShell title="Context" question="Where does every token go, and what's re-billed?">
        <ErrorCard />
      </PageShell>
    );
  }

  const regions = regionsQ.data?.regions ?? [];
  const waste = wasteQ.data;
  const totalTokens = regions.reduce((sum, r) => sum + Number(r.tokens), 0);
  const toolResultTokens =
    regions.find((r) => r.region === "tool_result")?.tokens ?? 0;
  const toolPct = totalTokens > 0 ? Math.round((toolResultTokens / totalTokens) * 100) : 0;

  if (regions.length === 0) {
    return (
      <PageShell title="Context" question="Where does every token go, and what's re-billed?">
        <EmptyCard
          title="No region data yet"
          detail="Sessions from this source don't expose context internals — check data notes after sync."
        />
      </PageShell>
    );
  }

  return (
    <PageShell title="Context" question="Where does every token go, and what's re-billed?">
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="card p-4">
            <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">Tool results share</p>
            <p className="mt-1 font-display text-2xl text-bone">{toolPct}%</p>
            <p className="mt-1 text-sm text-cinder">Your context is {toolPct}% tool results on average.</p>
          </div>
          <div className="card p-4">
            <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">Re-billed waste</p>
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

        <ChartFrame title="Context composition" subtitle="Tokens by region">
          <HorizontalBars
            items={regions.map((r) => ({
              label: REGION_LABELS[r.region] ?? r.region,
              value: Number(r.tokens),
            }))}
          />
        </ChartFrame>

        <ChartFrame title="Waste ledger" subtitle="Re-billing categories">
          {(waste?.categories ?? []).length > 0 ? (
            <HorizontalBars
              items={(waste?.categories ?? []).map((c) => ({
                label: c.category.replace(/_/g, " "),
                value: Number(c.tokens),
                to: `/insights?detector=${encodeURIComponent(c.category)}`,
              }))}
            />
          ) : (
            <p className="text-sm text-cinder">No waste categories recorded yet.</p>
          )}
          {waste && waste.total_waste_tokens > 0 ? (
            <p className="mt-4 text-sm text-cinder">
              Estimated re-billing cost: {formatCost(waste.total_waste_tokens * 0.000003)}
            </p>
          ) : null}
        </ChartFrame>
      </div>
    </PageShell>
  );
}
