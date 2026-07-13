import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  ArrowUpRight,
  CircleDollarSign,
  Layers3,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
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
      <PageShell title="Overview" question="Health, cost, and improvement signals across your agent workspace.">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell title="Overview" question="Health, cost, and improvement signals across your agent workspace.">
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
    waste: usageSeries.map((r: UsageSeriesRow) => Number(r.waste_tokens)),
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
  const totalTokens = inputTokens + outputTokens;
  const wasteRate = inputTokens > 0 ? (waste / inputTokens) * 100 : 0;
  const averageCost = traces > 0 ? cost / traces : 0;
  const recentSpend = spark.spend.slice(Math.floor(spark.spend.length / 2));
  const previousSpend = spark.spend.slice(0, Math.floor(spark.spend.length / 2));
  const recentSpendTotal = recentSpend.reduce((sum, value) => sum + value, 0);
  const previousSpendTotal = previousSpend.reduce((sum, value) => sum + value, 0);
  const spendDelta = previousSpendTotal > 0
    ? ((recentSpendTotal - previousSpendTotal) / previousSpendTotal) * 100
    : 0;
  const spendVelocity = Math.abs(spendDelta) > 999
    ? "Recent spend spike"
    : `${spendDelta >= 0 ? "+" : ""}${spendDelta.toFixed(1)}% recent velocity`;
  const pulseTitle = attention.length > 0
    ? `${attention.length} signal${attention.length === 1 ? "" : "s"} need your attention`
    : traces > 0
      ? "Your agent system is operating normally"
      : "Cairn is ready for its first sync";

  return (
    <PageShell title="Overview" question="Health, cost, and improvement signals across your agent workspace.">
      <div className="space-y-4">
        <section className="signal-panel relative grid overflow-hidden p-6 lg:grid-cols-[1fr_280px] lg:p-7">
          <div className="relative z-10 max-w-3xl">
            <div className="mb-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-patina">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" /> Workspace pulse
            </div>
            <h2 className="font-display text-2xl font-[720] tracking-[-0.04em] text-bone sm:text-3xl">
              {pulseTitle}
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-cinder">
              {traces > 0
                ? `${traces} sessions produced ${formatTokens(totalTokens)} tokens at ${formatCost(cost)} total cost. ${formatTokens(waste)} tokens were flagged as avoidable context.`
                : "Run a sync to turn local agent activity into cost, quality, context, and behavior signals."}
            </p>
            {data.narrative.length > 0 ? (
              <div className="mt-5 flex flex-wrap gap-2">
                {data.narrative.slice(0, 2).map((sentence, index) => (
                  <button
                    key={index}
                    type="button"
                    className="inline-flex items-center gap-2 rounded-sm border border-quartz-vein/80 bg-anthracite/40 px-3 py-2 text-left text-xs text-bone transition-colors hover:border-copper/50 hover:bg-granite/50"
                    onClick={() => navigate(sentence.filter?.view === "waste" ? "/sessions?sort=waste" : "/sessions")}
                  >
                    {sentence.text.replace("session(s)", "sessions")} <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-copper" />
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <div className="relative hidden items-center justify-center lg:flex" aria-hidden="true">
            <div className="signal-orb flex h-44 w-44 flex-col items-center justify-center rounded-full">
              <span className="font-display text-4xl font-bold tracking-[-0.06em] text-bone">{wasteRate.toFixed(1)}%</span>
              <span className="mt-1 font-mono text-[9px] uppercase tracking-[0.16em] text-cinder">context waste</span>
            </div>
          </div>
        </section>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi icon={<Activity />} label="Sessions" value={String(traces)} spark={spark.sessions} detail="Observed runs" accent="violet" />
          <Kpi icon={<CircleDollarSign />} label="Total spend" value={formatCost(cost)} spark={spark.spend} detail={spendVelocity} accent="blue" />
          <Kpi icon={<TriangleAlert />} label="Waste rate" value={`${wasteRate.toFixed(1)}%`} spark={spark.waste} detail={`${formatTokens(waste)} avoidable tokens`} accent="amber" estimated={waste > 0} />
          <Kpi icon={<Layers3 />} label="Cost / session" value={formatCost(averageCost)} detail={`${formatTokens(totalTokens)} total tokens`} accent="mint" />
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(320px,.75fr)]">
          {usageSeries.length > 1 ? (
            <ChartFrame
              title="Spend velocity"
              subtitle={`${days}-day model cost · scrub to inspect`}
              action={<span className="font-mono text-sm text-bone">{formatCost(cost)}</span>}
            >
              <StackedArea data={costStack} keys={["cost"]} xKey="day" width={900} height={260} />
            </ChartFrame>
          ) : <div className="card skeleton h-[350px]" />}

          <section className="card overflow-hidden">
            <div className="border-b border-quartz-vein/70 px-5 py-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="page-kicker">Priority queue</p>
                  <h3 className="font-display text-base font-semibold text-bone">What to look at next</h3>
                </div>
                <span className="rounded-full bg-copper/10 px-2 py-1 font-mono text-[10px] text-copper">{attention.length} open</span>
              </div>
            </div>
            {attention.length > 0 ? (
              <ul className="divide-y divide-quartz-vein/50">
                {attention.slice(0, 5).map((insight, index) => (
                  <li key={insight.insight_id}>
                    <Link to="/insights" className="group flex gap-3 px-5 py-4 transition-colors hover:bg-granite/20">
                      <span className="mt-0.5 font-mono text-[10px] text-ash">0{index + 1}</span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-medium text-bone group-hover:text-copper">{insight.title}</p>
                        <p className="mt-1 font-mono text-[9px] uppercase tracking-wide text-ash">{insight.detector}</p>
                      </div>
                      <Chip label={insight.severity} tone={insight.severity === "error" || insight.severity === "warning" ? "cinnabar" : "default"} />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="flex flex-col items-center px-6 py-12 text-center">
                <ShieldCheck className="h-8 w-8 text-malachite" strokeWidth={1.5} />
                <p className="mt-3 text-sm font-medium text-bone">No urgent signals</p>
                <p className="mt-1 text-xs text-cinder">Cairn will surface anomalies here.</p>
              </div>
            )}
          </section>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          {wasteItems.length > 0 ? (
            <ChartFrame title="Context waste" subtitle="Avoidable re-billing by category">
              <HorizontalBars items={wasteItems.slice(0, 6)} width={620} />
            </ChartFrame>
          ) : null}

          <ChartFrame title="Token economics" subtitle="How this window was allocated">
            <div className="grid grid-cols-3 gap-3">
              <TokenStat label="Input" value={inputTokens} total={totalTokens} color="bg-copper" />
              <TokenStat label="Output" value={outputTokens} total={totalTokens} color="bg-patina" />
              <TokenStat label="Waste" value={waste} total={totalTokens} color="bg-cinnabar" />
            </div>
            <div className="mt-6 flex h-2 overflow-hidden rounded-full bg-granite/60">
              <div className="bg-copper" style={{ width: `${totalTokens ? inputTokens / totalTokens * 100 : 0}%` }} />
              <div className="bg-patina" style={{ width: `${totalTokens ? outputTokens / totalTokens * 100 : 0}%` }} />
            </div>
            {data.tail_risk.expected_worst_cost != null ? (
              <div className="mt-6 flex items-center justify-between rounded-sm border border-quartz-vein/60 bg-anthracite/30 px-4 py-3">
                <div>
                  <p className="font-mono text-[9px] uppercase tracking-wide text-ash">Expected worst session</p>
                  <p className="mt-1 text-sm font-semibold text-bone">{formatCost(data.tail_risk.expected_worst_cost)}</p>
                </div>
                {tailExceedances.length > 0 ? <Sparkline data={tailExceedances} width={160} height={42} color={chartColors.fillWarn} /> : null}
              </div>
            ) : null}
          </ChartFrame>
        </div>

        {data.data_notes.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2 px-1 text-[11px] text-cinder">
            <span className="font-mono text-[9px] uppercase tracking-wide text-ash">Data notes</span>
            {data.data_notes.map((note, index) => <span key={index}><Chip label={note.source} /> {note.message}</span>)}
          </div>
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
  detail,
  icon,
  accent,
}: {
  label: string;
  value: string;
  spark?: number[];
  estimated?: boolean;
  detail?: string;
  icon: ReactNode;
  accent: "violet" | "blue" | "amber" | "mint";
}) {
  const accents = {
    violet: "text-copper bg-copper/10",
    blue: "text-lapis bg-lapis/10",
    amber: "text-ochre bg-ochre/10",
    mint: "text-patina bg-patina/10",
  };
  return (
    <div className={`card card--interactive metric-card p-5 ${estimated ? "estimated-chip" : ""}`}>
      <div className="flex items-center justify-between">
        <p className="font-mono text-[9px] uppercase tracking-[0.12em] text-cinder">{label}</p>
        <span className={`flex h-7 w-7 items-center justify-center rounded-sm [&>svg]:h-3.5 [&>svg]:w-3.5 ${accents[accent]}`}>{icon}</span>
      </div>
      <p className="mt-3 font-display text-[28px] font-[700] tracking-[-0.05em] text-bone">{value}</p>
      {detail ? <p className="mt-1 text-[11px] text-cinder">{detail}</p> : null}
      {spark && spark.length > 0 ? (
        <div className="mt-3">
          <Sparkline data={spark} width={180} height={30} />
        </div>
      ) : null}
    </div>
  );
}

function TokenStat({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const share = total > 0 ? value / total * 100 : 0;
  return (
    <div className="rounded-sm border border-quartz-vein/60 bg-anthracite/25 p-3">
      <div className="flex items-center gap-2"><span className={`h-1.5 w-1.5 rounded-full ${color}`} /><span className="font-mono text-[9px] uppercase tracking-wide text-cinder">{label}</span></div>
      <p className="mt-3 text-lg font-semibold tracking-[-0.03em] text-bone">{formatTokens(value)}</p>
      <p className="mt-0.5 font-mono text-[9px] text-ash">{share.toFixed(1)}% of total</p>
    </div>
  );
}
