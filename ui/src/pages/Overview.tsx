import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
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
  fetchOverview,
  fetchRecap,
  fetchTail,
  fetchUsage,
  fetchWaste,
  fetchWorkspace,
} from "@/lib/api";
import { formatCost, formatDecimal, formatNumber, formatPercent, formatTokens } from "@/lib/format";
import { useSelectedTimeRange } from "@/hooks/useSelectedTimeRange";
import type {
  MoneySummary,
  OverviewHero,
  RecapResponse,
  ShieldSummary,
  UsageSeriesRow,
  WasteCause,
} from "@/lib/types";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame, Chip } from "@/components/common/Chip";
import { HorizontalBars, Sparkline, StackedArea } from "@/components/charts";
import { chartColors } from "@/components/charts/chartTheme";
import { RECAP_VIEWED_KEY, recapPeriodKey, shouldShowRecap } from "@/lib/recap";
import { timeRangeLabel } from "@/lib/timeRange";
import { FirstRun } from "@/components/common/FirstRun";
import { useTimeRangeUrlState } from "@/hooks/useTimeRangeUrlState";
import { SidePanel } from "@/components/ui";

export function OverviewPage() {
  const { range, rangeKey } = useSelectedTimeRange();
  const rangeLabel = timeRangeLabel(range);
  const navigate = useNavigate();
  const { selectPreset } = useTimeRangeUrlState();
  const [showRecap, setShowRecap] = useState(() =>
    shouldShowRecap(localStorage.getItem(RECAP_VIEWED_KEY)),
  );
  const [selectedCause, setSelectedCause] = useState<WasteCause | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["overview", rangeKey],
    queryFn: () => fetchOverview(range),
  });

  const usageQ = useQuery({
    queryKey: ["usage", rangeKey],
    queryFn: () => fetchUsage(range),
  });

  const wasteQ = useQuery({
    queryKey: ["waste", rangeKey],
    queryFn: () => fetchWaste(range),
  });

  const tailQ = useQuery({
    queryKey: ["tail", rangeKey],
    queryFn: () => fetchTail(range),
  });

  const recapQ = useQuery({
    queryKey: ["recap"],
    queryFn: fetchRecap,
    enabled: showRecap,
  });
  const workspaceQ = useQuery({
    queryKey: ["workspace"],
    queryFn: fetchWorkspace,
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <PageShell
        title="Overview"
        question="Health, cost, and improvement signals across your agent workspace."
      >
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell
        title="Overview"
        question="Health, cost, and improvement signals across your agent workspace."
      >
        <div className="card p-6 text-cinnabar">
          Couldn&apos;t reach the local server — is <span className="mono">cairn ui</span> running?
        </div>
      </PageShell>
    );
  }

  if (workspaceQ.data?.health.trace_count === 0) {
    return (
      <PageShell
        title="Overview"
        question="Connect local agent activity, then turn it into cost, quality, context, and behavior evidence."
      >
        <FirstRun workspace={workspaceQ.data} />
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

  const attention = data.attention ?? [];
  const attentionCount = attention.reduce((sum, category) => sum + category.count, 0);

  const tailExceedances = tailQ.data?.exceedances ?? [];
  const totalTokens = inputTokens + outputTokens;
  const wasteRate = inputTokens > 0 ? (waste / inputTokens) * 100 : 0;
  const recentSpend = spark.spend.slice(Math.floor(spark.spend.length / 2));
  const previousSpend = spark.spend.slice(0, Math.floor(spark.spend.length / 2));
  const recentSpendTotal = recentSpend.reduce((sum, value) => sum + value, 0);
  const previousSpendTotal = previousSpend.reduce((sum, value) => sum + value, 0);
  const spendDelta =
    previousSpendTotal > 0
      ? ((recentSpendTotal - previousSpendTotal) / previousSpendTotal) * 100
      : 0;
  const spendVelocity =
    Math.abs(spendDelta) > 999
      ? "Recent spend spike"
      : `${spendDelta >= 0 ? "+" : ""}${formatPercent(spendDelta)} recent velocity`;
  const pulseTitle =
    attentionCount > 0
      ? `${attentionCount} signal${attentionCount === 1 ? "" : "s"} need your attention`
      : traces > 0
        ? "Your agent system is operating normally"
        : "Cairn is ready for its first sync";

  if (traces === 0 && workspaceQ.data && workspaceQ.data.health.trace_count > 0) {
    return (
      <PageShell
        title="Overview"
        question="Health, cost, and improvement signals across your agent workspace."
      >
        <div className="card p-6">
          <p className="page-kicker">Selected range</p>
          <h2 className="mt-1 font-display text-xl text-bone">No sessions in this time range</h2>
          <p className="mt-2 text-sm text-cinder">
            This workspace contains {workspaceQ.data.health.trace_count} session
            {workspaceQ.data.health.trace_count === 1 ? "" : "s"}, but none fall inside {rangeLabel}
            . Expand the range without re-importing data.
          </p>
          <button
            type="button"
            className="mt-4 min-h-10 rounded-sm bg-copper px-4 text-sm font-semibold text-anthracite"
            onClick={() => selectPreset("90d")}
          >
            Show 90 days
          </button>
        </div>
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Overview"
      question="Health, cost, and improvement signals across your agent workspace."
    >
      <div className="space-y-4">
        {workspaceQ.data?.root_path.replace(/\\/g, "/").endsWith("/.cairn-demo") ? (
          <section className="rounded-sm border border-patina/40 bg-patina/5 px-4 py-3">
            <p className="font-display text-sm text-bone">Deterministic demo workspace</p>
            <p className="mt-1 text-xs text-cinder">
              These synthetic sessions are isolated from real data. To return, stop this server and
              run{" "}
              <code className="font-mono text-patina">cairn ui --workspace /path/to/your-repo</code>
              .
            </p>
          </section>
        ) : null}
        {showRecap && recapQ.data ? (
          <RecapBanner
            recap={recapQ.data}
            onDismiss={() => {
              localStorage.setItem(RECAP_VIEWED_KEY, recapPeriodKey(recapQ.data.generated_at));
              setShowRecap(false);
            }}
          />
        ) : null}
        <MoneySlide
          money={data.money}
          hero={data.hero}
          shields={data.shields}
          onEvidence={setSelectedCause}
        />

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
                    onClick={() =>
                      navigate(
                        sentence.filter?.view === "waste" ? "/sessions?sort=waste" : "/sessions",
                      )
                    }
                  >
                    {sentence.text} <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-copper" />
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <div className="relative hidden items-center justify-center lg:flex" aria-hidden="true">
            <div className="signal-orb flex h-44 w-44 flex-col items-center justify-center rounded-full">
              <span className="font-display text-4xl font-bold tracking-[-0.06em] text-bone">
                {formatPercent(wasteRate)}
              </span>
              <span className="mt-1 font-mono text-[9px] uppercase tracking-[0.16em] text-cinder">
                context waste
              </span>
            </div>
          </div>
        </section>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi
            icon={<Activity />}
            label="Sessions"
            value={String(traces)}
            spark={spark.sessions}
            detail="Observed runs"
            accent="violet"
            delta={data.hero.deltas.sessions}
          />
          <Kpi
            icon={<CircleDollarSign />}
            label="Total spend"
            value={formatCost(cost)}
            spark={spark.spend}
            detail={spendVelocity}
            accent="blue"
            delta={data.hero.deltas.spend}
          />
          <Kpi
            icon={<TriangleAlert />}
            label="Waste rate"
            value={formatPercent(wasteRate)}
            spark={spark.waste}
            detail={`${formatTokens(waste)} avoidable tokens`}
            accent="amber"
            estimated={waste > 0}
            delta={data.hero.deltas.waste_rate}
          />
          <Kpi
            icon={<Layers3 />}
            label="Quality"
            value={
              data.hero.quality_mean == null ? "Unavailable" : formatDecimal(data.hero.quality_mean)
            }
            detail={`${data.hero.quality_sessions} scored session${data.hero.quality_sessions === 1 ? "" : "s"}`}
            accent="mint"
            delta={data.hero.deltas.quality}
            spark={data.hero.quality_sparkline}
          />
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(320px,.75fr)]">
          {usageSeries.length > 1 ? (
            <ChartFrame
              title="Spend velocity"
              subtitle={`${rangeLabel} · model cost · scrub to inspect`}
              action={<span className="font-mono text-sm text-bone">{formatCost(cost)}</span>}
              summary={`${formatCost(cost)} total spend is plotted across ${costStack.length} reporting periods.`}
              rows={costStack}
              columns={[
                { key: "day", label: "Day", value: (row) => row.day },
                {
                  key: "cost",
                  label: "Cost",
                  value: (row) => formatCost(row.cost, 4),
                  numeric: true,
                },
              ]}
            >
              <StackedArea
                data={costStack}
                keys={["cost"]}
                xKey="day"
                width={900}
                height={260}
                annotations={data.annotations.map((annotation) => ({
                  x: annotation.occurred_at.slice(5, 10),
                  label: annotation.label,
                }))}
              />
              {data.annotations.length > 0 ? (
                <ul className="mt-3 flex flex-wrap gap-2" aria-label="Spend annotations">
                  {data.annotations.map((annotation) => (
                    <li key={`${annotation.occurred_at}-${annotation.label}`}>
                      <Link
                        to={annotation.action_path}
                        className="rounded-chip border border-ochre/50 px-2 py-1 font-mono text-[10px] text-ochre"
                      >
                        {annotation.occurred_at.slice(0, 10)} · {annotation.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : null}
            </ChartFrame>
          ) : (
            <div className="card skeleton h-[350px]" />
          )}

          <section className="card overflow-hidden">
            <div className="border-b border-quartz-vein/70 px-5 py-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="page-kicker">Priority queue</p>
                  <h3 className="font-display text-base font-semibold text-bone">
                    What to look at next
                  </h3>
                </div>
                <span className="rounded-full bg-copper/10 px-2 py-1 font-mono text-[10px] text-copper">
                  {attentionCount} open
                </span>
              </div>
            </div>
            {attentionCount === 0 ? (
              <div className="flex flex-col items-center px-6 py-12 text-center">
                <ShieldCheck className="h-8 w-8 text-malachite" strokeWidth={1.5} />
                <p className="mt-3 text-sm font-medium text-bone">No recorded attention signals</p>
                <p className="mt-1 text-xs text-cinder">
                  Clear states use available evidence only; unavailable checks remain listed below.
                </p>
              </div>
            ) : null}
            <ul className="divide-y divide-quartz-vein/50">
              {attention.map((category) => (
                <li key={category.category} className="px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[13px] font-medium text-bone">{category.label}</p>
                      <p className="mt-1 text-xs leading-5 text-cinder">{category.summary}</p>
                    </div>
                    <Chip
                      label={
                        category.state === "attention" ? String(category.count) : category.state
                      }
                      tone={category.state === "attention" ? "cinnabar" : "estimated"}
                    />
                  </div>
                  {category.items.length > 0 ? (
                    <ul className="mt-2 space-y-2">
                      {category.items.map((item) => (
                        <li key={item.item_id}>
                          <Link
                            to={item.action_path}
                            className="group block rounded-sm border border-quartz-vein/70 px-3 py-2 hover:border-copper/50"
                          >
                            <span className="text-xs text-copper group-hover:underline">
                              {item.title}
                            </span>
                            <span className="mt-1 block text-[10px] leading-4 text-ash">
                              {item.detail}
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {category.limitation ? (
                    <p className="mt-2 text-[10px] leading-4 text-ash">
                      Limit: {category.limitation}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          {wasteItems.length > 0 ? (
            <ChartFrame
              title="Context waste"
              subtitle="Avoidable re-billing by category"
              summary={`${formatTokens(waste)} tokens were flagged as avoidable context; the chart ranks the leading categories.`}
              rows={wasteItems.slice(0, 6)}
              columns={[
                { key: "category", label: "Category", value: (row) => row.label },
                {
                  key: "tokens",
                  label: "Tokens",
                  value: (row) => formatNumber(row.value),
                  numeric: true,
                },
              ]}
            >
              <HorizontalBars items={wasteItems.slice(0, 6)} width={620} />
            </ChartFrame>
          ) : null}

          <ChartFrame
            title="Token economics"
            subtitle="How this window was allocated"
            summary={`${formatTokens(totalTokens)} total tokens comprise ${formatTokens(inputTokens)} input and ${formatTokens(outputTokens)} output tokens. ${formatTokens(waste)} input tokens were flagged as waste and are not added to the total.`}
            rows={[
              {
                category: "Input",
                tokens: inputTokens,
                share: totalTokens ? inputTokens / totalTokens : 0,
              },
              {
                category: "Output",
                tokens: outputTokens,
                share: totalTokens ? outputTokens / totalTokens : 0,
              },
              {
                category: "Waste (subset of input)",
                tokens: waste,
                share: totalTokens ? waste / totalTokens : 0,
              },
            ]}
            columns={[
              { key: "category", label: "Category", value: (row) => row.category },
              {
                key: "tokens",
                label: "Tokens",
                value: (row) => formatNumber(row.tokens),
                numeric: true,
              },
              {
                key: "share",
                label: "Share of total",
                value: (row) => formatPercent(row.share * 100),
                numeric: true,
              },
            ]}
          >
            <div className="grid grid-cols-3 gap-3">
              <TokenStat label="Input" value={inputTokens} total={totalTokens} color="bg-copper" />
              <TokenStat
                label="Output"
                value={outputTokens}
                total={totalTokens}
                color="bg-patina"
              />
              <TokenStat label="Waste" value={waste} total={totalTokens} color="bg-cinnabar" />
            </div>
            <div className="mt-6 flex h-2 overflow-hidden rounded-full bg-granite/60">
              <div
                className="bg-copper"
                style={{ width: `${totalTokens ? (inputTokens / totalTokens) * 100 : 0}%` }}
              />
              <div
                className="bg-patina"
                style={{ width: `${totalTokens ? (outputTokens / totalTokens) * 100 : 0}%` }}
              />
            </div>
            {data.tail_risk.expected_worst_cost != null ? (
              <div className="mt-6 flex items-center justify-between rounded-sm border border-quartz-vein/60 bg-anthracite/30 px-4 py-3">
                <div>
                  <p className="font-mono text-[9px] uppercase tracking-wide text-ash">
                    Expected worst session
                  </p>
                  <p className="mt-1 text-sm font-semibold text-bone">
                    {formatCost(data.tail_risk.expected_worst_cost)}
                  </p>
                </div>
                {tailExceedances.length > 0 ? (
                  <Sparkline
                    data={tailExceedances}
                    width={160}
                    height={42}
                    color={chartColors.fillWarn}
                  />
                ) : null}
              </div>
            ) : null}
          </ChartFrame>
        </div>

        {data.data_notes.length > 0 ? (
          <div className="flex flex-wrap items-center gap-2 px-1 text-[11px] text-cinder">
            <span className="font-mono text-[9px] uppercase tracking-wide text-ash">
              Data notes
            </span>
            {data.data_notes.map((note, index) => (
              <span key={index}>
                <Chip label={note.source} /> {note.message}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      <SidePanel
        open={selectedCause != null}
        title={selectedCause ? `${selectedCause.category.replace(/_/g, " ")} evidence` : "Evidence"}
        onClose={() => setSelectedCause(null)}
      >
        {selectedCause ? (
          <div>
            <p className="text-sm text-bone">{selectedCause.cause}</p>
            <p className="mt-2 text-sm text-patina">Suggested fix: {selectedCause.fix}</p>
            <p className="mt-2 text-xs text-cinder">
              {selectedCause.confidence} confidence: {selectedCause.confidence_explanation}
            </p>
            <p className="mt-3 text-xs text-cinder">
              Showing {selectedCause.evidence.length} of {selectedCause.evidence_count} supporting
              span{selectedCause.evidence_count === 1 ? "" : "s"}. Estimated impact allocates
              measured session cost in proportion to flagged waste tokens; it is not guaranteed
              savings.
            </p>
            {selectedCause.evidence.length > 0 ? (
              <ul className="mt-4 space-y-2">
                {selectedCause.evidence.map((evidence) => (
                  <li
                    key={`${evidence.trace_id}-${evidence.span_id}`}
                    className="rounded-sm border border-quartz-vein p-3"
                  >
                    <Link
                      to={`/sessions/${evidence.trace_id}${evidence.span_id ? `?span=${encodeURIComponent(evidence.span_id)}` : ""}`}
                      className="text-sm text-copper"
                      onClick={() => setSelectedCause(null)}
                    >
                      {evidence.label}
                    </Link>
                    <p className="mt-1 font-mono text-[10px] text-cinder">
                      {formatTokens(evidence.waste_tokens)} flagged tokens
                      {evidence.path_rel ? ` · ${evidence.path_rel}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 text-sm text-cinder">
                This aggregate category has no span-level evidence row in the selected range.
              </p>
            )}
          </div>
        ) : null}
      </SidePanel>
    </PageShell>
  );
}

export function RecapBanner({ recap, onDismiss }: { recap: RecapResponse; onDismiss: () => void }) {
  const top = recap.money.top_causes[0];
  const trend = recap.quality_trend;
  return (
    <section
      className="rounded-sm border border-patina/40 bg-patina/10 p-4"
      aria-label="Weekly recap"
    >
      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <p className="page-kicker text-patina">Your weekly Cairn recap</p>
          <p className="mt-2 text-sm text-bone">
            {formatCost(recap.money.total_spend_usd)} spent ·{" "}
            {formatCost(recap.money.wasted_spend_usd)} ± estimated waste
            {top ? ` · top cause: ${top.category.replace(/_/g, " ")}` : ""}
          </p>
          <p className="mt-1 text-xs text-cinder">
            Quality{" "}
            {trend.current_mean == null
              ? "awaiting scored sessions"
              : `${formatDecimal(trend.current_mean)}${
                  trend.delta == null
                    ? ""
                    : ` (${trend.delta >= 0 ? "+" : ""}${formatDecimal(trend.delta)})`
                }`}
            {` · ${recap.experiment_verdicts.length} experiment verdict${recap.experiment_verdicts.length === 1 ? "" : "s"} reached`}
          </p>
        </div>
        <Link
          to="/recap"
          className="rounded-sm bg-patina px-3 py-2 text-xs font-semibold text-anthracite"
        >
          Open full recap
        </Link>
        <button
          type="button"
          className="px-2 py-1 text-sm text-cinder hover:text-bone"
          onClick={onDismiss}
          aria-label="Dismiss weekly recap"
        >
          ×
        </button>
      </div>
    </section>
  );
}

export function MoneySlide({
  money,
  hero,
  shields = [],
  onEvidence,
}: {
  money: MoneySummary;
  hero?: OverviewHero;
  shields?: ShieldSummary[];
  onEvidence?: (cause: WasteCause) => void;
}) {
  return (
    <section className="card overflow-hidden border-copper/35">
      {hero ? (
        <div className="border-b border-quartz-vein/70 bg-copper/5 p-6 lg:p-7">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="page-kicker">Money and quality</p>
              <h2 className="font-display text-xl text-bone">
                What this window cost, and what success cost
              </h2>
            </div>
            <Chip
              label={
                hero.budget.state === "unconfigured"
                  ? "Budget not configured"
                  : `Budget ${hero.budget.state}`
              }
              tone={
                hero.budget.state === "over" || hero.budget.state === "attention"
                  ? "cinnabar"
                  : "default"
              }
            />
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <HeroMetric label="Spend" value={formatCost(money.total_spend_usd)} />
            <HeroMetric
              label="Avoidable spend"
              value={formatCost(money.wasted_spend_usd)}
              detail={`${formatPercent(money.wasted_spend_pct)} · estimated`}
            />
            <HeroMetric
              label="Quality"
              value={hero.quality_mean == null ? "Unavailable" : formatDecimal(hero.quality_mean)}
              detail={`${hero.quality_sessions} scored`}
            />
            <HeroMetric
              label="Cost / success"
              value={
                hero.cost_per_success_usd == null
                  ? "Unavailable"
                  : formatCost(hero.cost_per_success_usd)
              }
              detail={`${hero.successful_sessions} measured`}
            />
            <HeroMetric
              label="Month end (linear)"
              value={
                hero.projection.projected_usd == null
                  ? hero.projection.state === "not_current_period"
                    ? "Not current period"
                    : "Insufficient history"
                  : formatCost(hero.projection.projected_usd)
              }
              detail={hero.projection.explanation}
            />
          </div>
          {(hero.projection.trailing_7d_projected_usd != null ||
            hero.projection.projected_overrun_date != null) && (
            <div className="mt-3 flex flex-wrap gap-4 text-xs text-cinder">
              {hero.projection.trailing_7d_projected_usd != null ? (
                <span>
                  Trailing 7d month-end:{" "}
                  <span className="font-mono text-bone">
                    {formatCost(hero.projection.trailing_7d_projected_usd)}
                  </span>
                </span>
              ) : null}
              {hero.projection.projected_overrun_date != null ? (
                <span>
                  Projected overrun (linear, descriptive):{" "}
                  <span className="font-mono text-bone">
                    {hero.projection.projected_overrun_date}
                  </span>
                </span>
              ) : null}
            </div>
          )}
          <p className="mt-3 text-xs text-cinder">{hero.budget.explanation}</p>
        </div>
      ) : null}
      <div className="grid gap-5 p-6 lg:grid-cols-[260px_1fr] lg:p-7">
        <div>
          <p className="page-kicker">Last {money.period_days} days · money slide</p>
          <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-1">
            <div>
              <div className="flex items-center gap-2">
                <p className="font-mono text-[9px] uppercase tracking-wide text-cinder">
                  Total spend
                </p>
                {money.spend_estimated ? <Chip label="± estimated" tone="estimated" /> : null}
              </div>
              <p className="mt-1 font-display text-3xl font-bold tracking-[-0.05em] text-bone">
                {formatCost(money.total_spend_usd)}
              </p>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <p className="font-mono text-[9px] uppercase tracking-wide text-cinder">
                  Wasted spend
                </p>
                {money.waste_estimated ? <Chip label="± estimated" tone="estimated" /> : null}
              </div>
              <p className="mt-1 font-display text-3xl font-bold tracking-[-0.05em] text-ochre">
                {formatCost(money.wasted_spend_usd)}
                <span className="ml-2 text-base text-cinder">
                  {formatPercent(money.wasted_spend_pct)}
                </span>
              </p>
            </div>
          </div>
          <Link
            to={money.primary_action}
            className="mt-5 inline-flex items-center gap-2 rounded-sm bg-copper px-4 py-2.5 text-sm font-semibold text-anthracite hover:bg-copper/90"
          >
            Review proposed fix <ArrowUpRight className="h-4 w-4" />
          </Link>
        </div>
        <div>
          <p className="font-mono text-[9px] uppercase tracking-wide text-cinder">
            Top waste causes
          </p>
          {money.top_causes.length > 0 ? (
            <ol className="mt-3 divide-y divide-quartz-vein/60 rounded-sm border border-quartz-vein/70">
              {money.top_causes.map((item, index) => (
                <li
                  key={item.category}
                  className="grid gap-2 px-4 py-3 sm:grid-cols-[32px_92px_1fr_auto]"
                >
                  <span className="font-mono text-xs text-ash">0{index + 1}</span>
                  <span className="font-mono text-sm font-semibold text-ochre">
                    {formatCost(item.estimated_savings_usd)}
                  </span>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm text-bone">{item.cause}</p>
                      <Chip label={`${item.confidence} confidence`} tone="estimated" />
                    </div>
                    <p className="mt-1 text-[10px] leading-4 text-ash">
                      {item.confidence_explanation}
                    </p>
                    <p className="mt-1 text-xs text-patina">Fix: {item.fix}</p>
                  </div>
                  {onEvidence ? (
                    <div className="flex flex-wrap items-center gap-2 self-center">
                      <button
                        type="button"
                        className="min-h-9 rounded-sm bg-copper px-3 text-xs font-semibold text-anthracite"
                        onClick={() => onEvidence(item)}
                      >
                        Review fix
                      </button>
                      <button
                        type="button"
                        className="min-h-9 rounded-sm border border-quartz-vein px-3 text-xs text-bone"
                        onClick={() => onEvidence(item)}
                      >
                        Evidence ({item.evidence_count})
                      </button>
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : (
            <div className="mt-3 rounded-sm border border-dashed border-quartz-vein p-5 text-sm text-cinder">
              No priced waste cause yet. Sync a session with token and cost data to populate this
              list.
            </div>
          )}
        </div>
      </div>
      {shields.length > 0 ? (
        <div className="border-t border-quartz-vein/70 p-6 lg:p-7">
          <p className="font-mono text-[9px] uppercase tracking-wide text-cinder">
            Cairn shields · independent facts, not one trust score
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {shields.map((shield) => (
              <article key={shield.shield} className="rounded-sm border border-quartz-vein p-4">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="font-display text-sm capitalize text-bone">
                    {shield.shield} shield
                  </h3>
                  <Chip
                    label={shield.state}
                    tone={shield.state === "attention" ? "cinnabar" : "estimated"}
                  />
                </div>
                <p className="mt-2 text-xs text-bone">{shield.summary}</p>
                <ul className="mt-2 space-y-1 text-xs text-cinder">
                  {shield.facts.map((fact) => (
                    <li key={fact}>• {fact}</li>
                  ))}
                </ul>
                <p className="mt-2 text-[11px] text-ash">Limit: {shield.limitation}</p>
                <Link
                  to={shield.action_path}
                  className="mt-3 inline-flex text-xs text-copper hover:underline"
                >
                  {shield.action_label}
                </Link>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function HeroMetric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-sm border border-quartz-vein/70 bg-anthracite/20 p-3">
      <p className="font-mono text-[9px] uppercase tracking-wide text-cinder">{label}</p>
      <p className="mt-2 font-display text-lg font-semibold text-bone">{value}</p>
      {detail ? <p className="mt-1 text-[10px] leading-4 text-ash">{detail}</p> : null}
    </div>
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
  delta,
}: {
  label: string;
  value: string;
  spark?: number[];
  estimated?: boolean;
  detail?: string;
  icon: ReactNode;
  accent: "violet" | "blue" | "amber" | "mint";
  delta?: OverviewHero["deltas"][string];
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
        <span
          className={`flex h-7 w-7 items-center justify-center rounded-sm [&>svg]:h-3.5 [&>svg]:w-3.5 ${accents[accent]}`}
        >
          {icon}
        </span>
      </div>
      <p className="mt-3 font-display text-[28px] font-[700] tracking-[-0.05em] text-bone">
        {value}
      </p>
      {detail ? <p className="mt-1 text-[11px] text-cinder">{detail}</p> : null}
      {delta ? (
        <p className="mt-1 font-mono text-[9px] text-ash">
          {delta.state === "available" && delta.delta_pct != null
            ? `${delta.delta_pct >= 0 ? "+" : ""}${formatPercent(delta.delta_pct)} vs equal prior period`
            : delta.state === "no_previous"
              ? "No prior-period baseline"
              : "Prior-period comparison unavailable"}
        </p>
      ) : null}
      {spark && spark.length > 0 ? (
        <div className="mt-3">
          <Sparkline data={spark} width={180} height={30} />
        </div>
      ) : null}
    </div>
  );
}

function TokenStat({
  label,
  value,
  total,
  color,
}: {
  label: string;
  value: number;
  total: number;
  color: string;
}) {
  const share = total > 0 ? (value / total) * 100 : 0;
  return (
    <div className="rounded-sm border border-quartz-vein/60 bg-anthracite/25 p-3">
      <div className="flex items-center gap-2">
        <span className={`h-1.5 w-1.5 rounded-full ${color}`} />
        <span className="font-mono text-[9px] uppercase tracking-wide text-cinder">{label}</span>
      </div>
      <p className="mt-3 text-lg font-semibold tracking-[-0.03em] text-bone">
        {formatTokens(value)}
      </p>
      <p className="mt-0.5 font-mono text-[9px] text-ash">{formatPercent(share)} of total</p>
    </div>
  );
}
