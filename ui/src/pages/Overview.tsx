import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchInsights,
  fetchOverview,
  fetchTail,
  fetchUsage,
  fetchWaste,
  timeRangeDays,
} from "@/lib/api";
import { formatCost, formatTokens } from "@/lib/format";
import { useUiStore } from "@/state/ui";
import type { UsageSeriesRow } from "@/lib/types";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame, Chip } from "@/components/common/Chip";
import {
  HorizontalBars,
  Sparkline,
  StackedArea,
} from "@/components/charts";
import { chartColors } from "@/components/charts/chartTheme";

export function OverviewPage() {
  const timeRange = useUiStore((s) => s.timeRange);
  const days = timeRangeDays(timeRange);
  const navigate = useNavigate();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["overview", days],
    queryFn: () => fetchOverview(days),
  });

  const usageQ = useQuery({
    queryKey: ["usage", days],
    queryFn: () => fetchUsage(days),
  });

  const wasteQ = useQuery({
    queryKey: ["waste", days],
    queryFn: () => fetchWaste(days),
  });

  const tailQ = useQuery({
    queryKey: ["tail", days],
    queryFn: () => fetchTail(days),
  });

  const insightsQ = useQuery({
    queryKey: ["insights", "overview"],
    queryFn: () => fetchInsights(),
  });

  if (isLoading) {
    return (
      <PageShell title="Overview" question="What happened, and what should I look at?">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell title="Overview" question="What happened, and what should I look at?">
        <div className="card p-6 text-cinnabar">
          Couldn&apos;t reach the local server — is <span className="mono">cairn ui</span> running?
        </div>
      </PageShell>
    );
  }

  const usageSeries = usageQ.data?.series ?? [];
  const traces = Number(data.kpis.traces ?? 0);
  const cost = Number(data.kpis.cost ?? 0);
  const inputTokens = Number(data.kpis.input_tokens ?? 0);
  const outputTokens = Number(data.kpis.output_tokens ?? 0);
  const waste = Number(data.kpis.waste_tokens ?? 0);

  const spark = {
    sessions: usageSeries.map((r: UsageSeriesRow) => Number(r.traces)),
    spend: usageSeries.map((r: UsageSeriesRow) => Number(r.cost)),
    input: usageSeries.map((r: UsageSeriesRow) => Number(r.input_tokens)),
    output: usageSeries.map((r: UsageSeriesRow) => Number(r.output_tokens)),
    waste: usageSeries.map((r: UsageSeriesRow) => Number(r.input_tokens) * 0.05),
  };

  const costStack = usageSeries.map((r: UsageSeriesRow) => ({
    day: r.key.slice(5) || r.key,
    cost: Number(r.cost),
  }));

  const wasteItems = (wasteQ.data?.categories ?? []).slice(0, 8).map((c) => ({
    label: c.category.replace(/_/g, " "),
    value: Number(c.tokens),
  }));

  const attention = (insightsQ.data?.insights ?? []).filter(
    (i) => i.state === "new" || i.severity === "warning" || i.severity === "error",
  ).slice(0, 6);

  const tailExceedances = tailQ.data?.exceedances ?? [];

  return (
    <PageShell title="Overview" question="What happened, and what should I look at?">
      <div className="space-y-6">
        <div className="card p-6">
          {data.narrative.length > 0 ? (
            <div className="space-y-2">
              {data.narrative.map((sentence, i) => (
                <button
                  key={i}
                  type="button"
                  className="display block text-left text-lg text-bone hover:text-copper"
                  onClick={() => {
                    if (sentence.filter?.days) {
                      navigate(`/sessions?days=${sentence.filter.days}`);
                    } else if (sentence.filter?.view === "waste") {
                      navigate("/sessions?sort=waste");
                    } else {
                      navigate("/sessions");
                    }
                  }}
                >
                  {sentence.text}
                </button>
              ))}
            </div>
          ) : (
            <p className="display text-xl text-bone">
              No sessions yet — run <span className="mono text-copper">cairn sync</span> to begin.
            </p>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Kpi label="Sessions" value={String(traces)} spark={spark.sessions} />
          <Kpi label="Spend" value={formatCost(cost)} spark={spark.spend} />
          <Kpi label="Input tokens" value={formatTokens(inputTokens)} spark={spark.input} />
          <Kpi label="Output tokens" value={formatTokens(outputTokens)} spark={spark.output} />
          <Kpi label="Waste" value={formatTokens(waste)} spark={spark.waste} estimated={waste > 0} />
        </div>

        {usageSeries.length > 1 ? (
          <ChartFrame title="Daily spend" subtitle={`${days}-day cost trend`}>
            <StackedArea
              data={costStack}
              keys={["cost"]}
              xKey="day"
              width={640}
              height={180}
            />
          </ChartFrame>
        ) : null}

        {wasteItems.length > 0 ? (
          <ChartFrame title="Waste categories" subtitle="Re-billing by category">
            <HorizontalBars items={wasteItems} width={480} />
          </ChartFrame>
        ) : null}

        {attention.length > 0 ? (
          <ChartFrame title="Needs attention" subtitle="New and warning insights">
            <ul className="divide-y divide-quartz-vein/50">
              {attention.map((insight) => (
                <li key={insight.insight_id}>
                  <Link
                    to="/insights"
                    className="flex items-start justify-between gap-4 px-1 py-3 hover:bg-granite/20"
                  >
                    <div>
                      <p className="text-sm text-bone">{insight.title}</p>
                      <p className="mt-0.5 font-mono text-[10px] text-cinder">{insight.detector}</p>
                    </div>
                    <Chip
                      label={insight.severity}
                      tone={
                        insight.severity === "error" || insight.severity === "warning"
                          ? "cinnabar"
                          : "default"
                      }
                    />
                  </Link>
                </li>
              ))}
            </ul>
          </ChartFrame>
        ) : null}

        {tailExceedances.length > 0 || data.tail_risk.expected_worst_cost != null ? (
          <ChartFrame title="Tail risk" subtitle="Cost exceedances above 90th percentile">
            <div className="flex flex-wrap items-end gap-6">
              {data.tail_risk.expected_worst_cost != null ? (
                <p className="font-mono text-sm text-ochre">
                  {formatCost(data.tail_risk.expected_worst_cost)} expected worst
                </p>
              ) : null}
              {tailExceedances.length > 0 ? (
                <Sparkline
                  data={tailExceedances}
                  width={200}
                  height={48}
                  color={chartColors.fillWarn}
                />
              ) : null}
            </div>
          </ChartFrame>
        ) : null}

        {data.data_notes.length > 0 ? (
          <div className="card p-4">
            <h3 className="font-mono text-[10px] uppercase tracking-wide text-cinder">Data notes</h3>
            <ul className="mt-2 space-y-2 text-sm text-cinder">
              {data.data_notes.map((note, i) => (
                <li key={i}>
                  <Chip label={note.source} /> {note.message}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {traces > 0 ? (
          <Link
            to="/sessions"
            className="inline-flex font-mono text-sm text-copper hover:underline"
          >
            View all sessions →
          </Link>
        ) : null}
      </div>
    </PageShell>
  );
}

function Kpi({
  label,
  value,
  spark,
  estimated,
}: {
  label: string;
  value: string;
  spark?: number[];
  estimated?: boolean;
}) {
  return (
    <div className={`card p-4 ${estimated ? "estimated-chip" : ""}`}>
      <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">{label}</p>
      <p className="mt-1 font-display text-2xl text-bone">{value}</p>
      {spark && spark.length > 0 ? (
        <div className="mt-2">
          <Sparkline data={spark} width={120} height={28} />
        </div>
      ) : null}
    </div>
  );
}
