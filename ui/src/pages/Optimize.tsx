import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChartFrame, IntervalPlot, Sparkline } from "@/components/charts";
import { Chip } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { PageShell } from "@/components/common/PageShell";
import { VerdictPreview } from "@/components/optimize/VerdictPreview";
import { EstimateBadge, Stat } from "@/components/ui";
import { fetchExperimentDetail, fetchExperiments, runAction } from "@/lib/api";
import {
  formatDate,
  formatDecimal,
  formatNumber,
  formatPercent,
  formatRelative,
} from "@/lib/format";
import type { ExperimentRow, VerdictPreviewData } from "@/lib/types";
import { useToastStore } from "@/state/toast";

const STATIONS = ["proposed", "applied", "measuring", "verdict"] as const;
type Tab = "board" | "portfolio";

function asTab(value: string | null): Tab {
  return value === "portfolio" ? "portfolio" : "board";
}

export function ExperimentLifecycle({
  status,
  appliedAt,
  nEffective,
  target,
  verdict,
  ciLow,
  ciHigh,
}: {
  status: string;
  appliedAt: string | null;
  nEffective: number | null;
  target: number;
  verdict: string | null;
  ciLow: number | null;
  ciHigh: number | null;
}) {
  const rank = Math.max(0, STATIONS.indexOf(status as (typeof STATIONS)[number]));
  const labels = [
    "Proposed",
    appliedAt ? `Applied ${formatDate(appliedAt)}` : "Applied",
    `Measuring n=${formatDecimal(nEffective ?? 0)}/${target}`,
    verdict
      ? `Verdict ${verdict}${ciLow != null && ciHigh != null ? ` · CI ${formatPercent(ciLow * 100)} to ${formatPercent(ciHigh * 100)}` : ""}`
      : "Verdict",
  ];
  return (
    <ol className="mt-4 grid gap-2 sm:grid-cols-4" aria-label="Experiment lifecycle">
      {labels.map((label, index) => (
        <li
          key={STATIONS[index]}
          className={`rounded-sm border px-2 py-2 font-mono text-[10px] ${
            index <= rank
              ? "border-copper/50 bg-copper/10 text-bone"
              : "border-quartz-vein text-ash"
          }`}
        >
          <span className="mr-1 text-copper">
            {index < rank ? "✓" : index === rank ? "●" : "○"}
          </span>
          {label}
        </li>
      ))}
    </ol>
  );
}


function ExperimentCard({
  experiment,
  initialExpanded = false,
  onApply,
  onRevert,
  onMeasure,
}: {
  experiment: ExperimentRow;
  initialExpanded?: boolean;
  onApply: () => void;
  onRevert: () => void;
  onMeasure: () => void;
}) {
  const [expanded, setExpanded] = useState(initialExpanded);
  const detailQ = useQuery({
    queryKey: ["experiment", experiment.experiment_id],
    queryFn: () => fetchExperimentDetail(experiment.experiment_id),
    enabled: expanded,
  });

  const exp = detailQ.data?.experiment;
  const detailPreview = detailQ.data?.preview as VerdictPreviewData | null | undefined;
  const writeSafety = detailQ.data?.write_safety;
  const guardLimitation = detailQ.data?.guard_limitation;
  const content = typeof exp?.content === "string" ? exp.content : null;
  const liftCiLow =
    experiment.effect_ci_low ?? (exp?.effect_ci_low != null ? Number(exp.effect_ci_low) : null);
  const liftCiHigh =
    experiment.effect_ci_high ?? (exp?.effect_ci_high != null ? Number(exp.effect_ci_high) : null);
  const liftEstimate =
    experiment.lift_pct ?? (exp?.effect_estimate != null ? Number(exp.effect_estimate) : null);
  const plain =
    experiment.plain_verdict ?? (typeof exp?.plain_verdict === "string" ? exp.plain_verdict : null);
  const history =
    experiment.effect_history.length > 0
      ? experiment.effect_history
      : Array.isArray(exp?.effect_history)
        ? (exp.effect_history as number[])
        : [];
  const nEff = experiment.sample_size ?? experiment.outcome_n_effective;
  const verdictHistory = experiment.verdict_history ?? [];

  return (
    <div className="card p-4" id={`experiment-${experiment.experiment_id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Chip
          label={experiment.status}
          tone={experiment.status === "verdict" ? "malachite" : "default"}
        />
        {experiment.target_file ? <Chip label={experiment.target_file} /> : null}
        {experiment.verdict ? <Chip label={experiment.verdict} tone="copper" /> : null}
        <Chip
          label={experiment.proposal_source === "provider" ? "provider" : "local"}
          tone="default"
        />
        {experiment.decay_state !== "unknown" ? (
          <Chip
            label={experiment.decay_state}
            tone={experiment.decay_state === "healthy" ? "malachite" : "copper"}
          />
        ) : null}
        {experiment.regression_outside_interval ? (
          <Chip label="outside prior interval" tone="copper" />
        ) : null}
        {experiment.confound_flag ? <Chip label="confounded" tone="copper" /> : null}
      </div>

      {plain ? (
        <p className="mt-3 text-sm text-bone" data-testid="plain-verdict">
          {plain}
        </p>
      ) : null}

      <p className="mt-2 font-mono text-xs text-cinder">
        {experiment.experiment_id.slice(0, 12)}… · {formatRelative(experiment.created_at)}
        {nEff != null ? ` · n_eff=${formatDecimal(nEff)}` : ""}
        {` · interval=${experiment.eval_interval_days ?? 30}d`}
        {experiment.last_evaluated_at
          ? ` · evaluated ${formatRelative(experiment.last_evaluated_at)}`
          : ""}
      </p>

      <ExperimentLifecycle
        status={experiment.status}
        appliedAt={experiment.applied_at}
        nEffective={experiment.outcome_n_effective}
        target={experiment.min_holdout}
        verdict={experiment.verdict}
        ciLow={liftCiLow}
        ciHigh={liftCiHigh}
      />

      {experiment.status === "proposed" && detailPreview ? (
        <VerdictPreview preview={detailPreview} />
      ) : null}

      {history.length > 1 ? (
        <div className="mt-3">
          <ChartFrame
            title="Effect history"
            subtitle="Sequential measured effect estimates"
            summary={`Effect history has ${history.length} points; latest ${formatPercent((history[history.length - 1] ?? 0) * 100)}.`}
            rows={history.map((value, index) => ({
              label: `m${index + 1}`,
              value,
            }))}
            columns={[
              { key: "measure", label: "Measure", value: (row) => row.label },
              {
                key: "estimate",
                label: "Estimate",
                value: (row) => formatPercent(row.value * 100),
                numeric: true,
              },
            ]}
          >
            <Sparkline data={history} width={320} height={48} />
          </ChartFrame>
        </div>
      ) : null}

      {verdictHistory.length > 0 ? (
        <div className="mt-3" data-testid="verdict-history">
          <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">
            Historical verdicts
          </p>
          <ul className="mt-1 space-y-1 font-mono text-[11px] text-cinder">
            {verdictHistory
              .slice(-5)
              .reverse()
              .map((entry) => (
                <li key={`${entry.at}-${entry.verdict ?? "none"}`}>
                  {formatRelative(entry.at)} · {entry.verdict ?? "unset"}
                  {entry.effect_estimate != null
                    ? ` · ${formatPercent(entry.effect_estimate * 100)}`
                    : ""}
                  {entry.sample_size != null ? ` · n=${formatDecimal(entry.sample_size)}` : ""}
                </li>
              ))}
          </ul>
        </div>
      ) : null}

      {liftEstimate != null ? (
        <div className="mt-3 flex items-center gap-2">
          <p className="font-mono text-sm text-bone">Effect: {formatPercent(liftEstimate * 100)}</p>
          <EstimateBadge label="Holdout estimate" />
        </div>
      ) : null}

      {liftCiLow != null && liftCiHigh != null && liftEstimate != null ? (
        <div className="mt-3">
          <ChartFrame
            title="Measured effect"
            subtitle="Estimate and confidence interval"
            summary={`Estimated lift is ${formatPercent(liftEstimate * 100)}, with an interval from ${formatPercent(liftCiLow * 100)} to ${formatPercent(liftCiHigh * 100)}.`}
            rows={[{ label: "Lift", value: liftEstimate, low: liftCiLow, high: liftCiHigh }]}
            columns={[
              { key: "measure", label: "Measure", value: (row) => row.label },
              {
                key: "estimate",
                label: "Estimate",
                value: (row) => formatPercent(row.value * 100),
                numeric: true,
              },
              {
                key: "low",
                label: "Interval low",
                value: (row) => formatPercent(row.low * 100),
                numeric: true,
              },
              {
                key: "high",
                label: "Interval high",
                value: (row) => formatPercent(row.high * 100),
                numeric: true,
              },
            ]}
          >
            <IntervalPlot
              points={[
                {
                  label: "lift",
                  value: liftEstimate,
                  low: liftCiLow,
                  high: liftCiHigh,
                },
              ]}
              width={320}
              height={80}
            />
          </ChartFrame>
        </div>
      ) : null}

      {experiment.confound_notes.length > 0 ? (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-cinder">
          {experiment.confound_notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}

      <p className="mt-3 text-xs text-cinder">
        {experiment.guard_event_id ? (
          <Link
            className="text-copper hover:underline"
            to={`/guard?event=${experiment.guard_event_id}`}
          >
            Guard event {experiment.guard_event_id.slice(0, 12)}…
          </Link>
        ) : (
          (guardLimitation ??
          "No matching Guard instruction-file event is linked to this rule yet.")
        )}
      </p>

      <button
        type="button"
        className="mt-2 font-mono text-[10px] text-copper hover:underline"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? "Hide diff" : "Preview diff"}
      </button>
      {expanded && content ? (
        <pre className="mt-2 max-h-48 overflow-auto rounded-sm bg-granite/40 p-3 font-mono text-[10px] text-bone">
          {content.slice(0, 2000)}
        </pre>
      ) : null}
      {expanded && writeSafety ? <p className="mt-2 text-xs text-cinder">{writeSafety}</p> : null}
      {expanded && !content && detailQ.isLoading ? (
        <p className="mt-2 text-xs text-cinder">Loading content…</p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        {experiment.status === "proposed" ? (
          <button
            type="button"
            className="rounded-sm bg-copper px-3 py-1.5 font-mono text-xs text-anthracite"
            onClick={onApply}
          >
            Apply
          </button>
        ) : null}
        {experiment.status === "applied" || experiment.status === "measuring" ? (
          <>
            <button
              type="button"
              className="rounded-sm bg-copper px-3 py-1.5 font-mono text-xs text-anthracite"
              onClick={onMeasure}
            >
              Measure now
            </button>
            <button
              type="button"
              className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-bone"
              onClick={onRevert}
            >
              Revert
            </button>
          </>
        ) : null}
        {experiment.status === "verdict" ? (
          <button
            type="button"
            className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-bone"
            onClick={onRevert}
          >
            Safe revert
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function OptimizePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedExperiment = searchParams.get("experiment");
  const tab = asTab(searchParams.get("tab"));
  const queryClient = useQueryClient();
  const showToast = useToastStore((s) => s.show);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["experiments"],
    queryFn: fetchExperiments,
  });

  const applyMut = useMutation({
    mutationFn: (id: string) => runAction("experiment_apply", { experiment_id: id }),
    onSuccess: () => {
      showToast("Experiment applied");
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
    onError: () => showToast("Apply failed", undefined, "error"),
  });

  const revertMut = useMutation({
    mutationFn: (id: string) => runAction("experiment_revert", { experiment_id: id }),
    onSuccess: () => {
      showToast("Experiment reverted", () => undefined);
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
    onError: () => showToast("Revert failed", undefined, "error"),
  });

  const measureMut = useMutation({
    mutationFn: (id: string) => runAction("experiment_measure", { experiment_id: id }),
    onSuccess: () => {
      showToast("Experiment measured");
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
    onError: () => showToast("Measurement failed", undefined, "error"),
  });

  const proposeMut = useMutation({
    mutationFn: () => runAction("optimize_propose"),
    onSuccess: () => {
      showToast("Proposals generated");
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
    onError: () => showToast("Proposal generation failed", undefined, "error"),
  });

  const setTab = (next: Tab) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  const boardRows = useMemo(
    () =>
      data?.experiments.filter((row) =>
        STATIONS.includes(row.status as (typeof STATIONS)[number]),
      ) ?? [],
    [data],
  );
  const portfolioRows = useMemo(
    () => data?.experiments.filter((row) => row.in_portfolio) ?? [],
    [data],
  );

  if (isLoading) {
    return (
      <PageShell
        title="Optimize"
        question="Turn evidence into controlled instruction changes, then prove whether they worked."
      >
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data?.ledger) {
    return (
      <PageShell
        title="Optimize"
        question="Turn evidence into controlled instruction changes, then prove whether they worked."
      >
        <ErrorCard />
      </PageShell>
    );
  }

  const { ledger } = data;
  const byStatus = STATIONS.reduce(
    (acc, s) => {
      acc[s] = boardRows.filter((e) => e.status === s);
      return acc;
    },
    {} as Record<(typeof STATIONS)[number], ExperimentRow[]>,
  );
  const visible = tab === "portfolio" ? portfolioRows : boardRows;

  return (
    <PageShell
      title="Optimize"
      question="Turn evidence into controlled instruction changes, then prove whether they worked."
    >
      <div className="space-y-6">
        <section className="card p-5" aria-labelledby="optimize-answer">
          <p className="page-kicker">Optimize ledger · workspace</p>
          <h2 id="optimize-answer" className="font-display text-xl text-bone">
            Controlled rules under holdout evidence
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-cinder">{ledger.conclusion}</p>
          <p className="mt-3 text-xs text-cinder">{ledger.limitation}</p>
          {ledger.next_action_href ? (
            <Link
              to={ledger.next_action_href}
              className="mt-4 inline-flex min-h-11 items-center font-mono text-xs text-copper"
            >
              {ledger.next_action}
            </Link>
          ) : (
            <p className="mt-4 font-mono text-xs text-cinder">{ledger.next_action}</p>
          )}
        </section>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat
            label="Proposed"
            value={formatNumber(ledger.proposed_count)}
            detail="Awaiting apply"
          />
          <Stat
            label="Active"
            value={formatNumber(ledger.active_count)}
            detail="Applied or measuring"
          />
          <Stat
            label="Portfolio"
            value={formatNumber(ledger.portfolio_count)}
            detail="Applied, measuring, verdict, reverted"
            help={{
              definition: "Rules that left the proposal column and enter the durable portfolio.",
              limitations: "Portfolio membership is status-based, not a performance ranking.",
            }}
          />
          <Stat
            label="Decaying / decayed"
            value={formatNumber(ledger.decayed_count)}
            detail="Descriptive age/confound flags"
            help={{
              definition: "Decay flags from age, confound, regression, or revert.",
              limitations: "Not a causal claim that the rule caused later metric changes.",
            }}
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2" role="tablist" aria-label="Optimize views">
            <button
              type="button"
              role="tab"
              aria-selected={tab === "board"}
              className={`rounded-sm border px-3 py-1.5 font-mono text-xs ${
                tab === "board"
                  ? "border-copper/50 bg-copper/10 text-bone"
                  : "border-quartz-vein text-cinder"
              }`}
              onClick={() => setTab("board")}
            >
              Board
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === "portfolio"}
              className={`rounded-sm border px-3 py-1.5 font-mono text-xs ${
                tab === "portfolio"
                  ? "border-copper/50 bg-copper/10 text-bone"
                  : "border-quartz-vein text-cinder"
              }`}
              onClick={() => setTab("portfolio")}
            >
              Portfolio
            </button>
          </div>
          <button
            type="button"
            className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone hover:bg-granite"
            onClick={() => proposeMut.mutate()}
          >
            Generate proposals
          </button>
        </div>

        {tab === "board" ? (
          <div className="card p-4">
            <div className="flex flex-wrap items-center gap-2">
              {STATIONS.map((station, i) => (
                <div key={station} className="flex items-center gap-2">
                  <div
                    className={`min-w-[100px] rounded-sm border px-3 py-2 text-center ${
                      byStatus[station].length > 0
                        ? "border-copper/50 bg-copper/10"
                        : "border-quartz-vein bg-granite/20"
                    }`}
                  >
                    <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">
                      {station}
                    </p>
                    <p className="mt-0.5 font-display text-xl text-bone">
                      {byStatus[station].length}
                    </p>
                  </div>
                  {i < STATIONS.length - 1 ? (
                    <span className="font-mono text-cinder" aria-hidden="true">
                      →
                    </span>
                  ) : null}
                </div>
              ))}
            </div>
            <p className="mt-3 border-t border-quartz-vein/50 pt-3 font-mono text-[10px] text-cinder">
              Reflector: proposals flow left-to-right — apply to measure, measure to verdict.
            </p>
          </div>
        ) : null}

        {visible.length === 0 ? (
          <EmptyCard
            title={tab === "portfolio" ? "Portfolio empty" : "No proposals yet"}
            detail={
              tab === "portfolio"
                ? "Apply a proposal to start measuring holdout effect before it appears here."
                : "Cairn needs about a week of sessions to find leverage. Run sync and check Insights first."
            }
            action={
              tab === "board" ? (
                <button
                  type="button"
                  className="rounded-sm bg-copper px-3 py-2 font-mono text-xs text-anthracite"
                  onClick={() => proposeMut.mutate()}
                >
                  Generate proposals
                </button>
              ) : undefined
            }
          />
        ) : (
          <div className="space-y-3">
            {visible.map((exp) => (
              <ExperimentCard
                key={exp.experiment_id}
                experiment={exp}
                initialExpanded={selectedExperiment === exp.experiment_id}
                onApply={() => applyMut.mutate(exp.experiment_id)}
                onRevert={() => revertMut.mutate(exp.experiment_id)}
                onMeasure={() => measureMut.mutate(exp.experiment_id)}
              />
            ))}
          </div>
        )}

        {data.limitations.length > 0 ? (
          <section className="card p-4" aria-label="Optimize limitations">
            <h3 className="font-display text-sm text-bone">Limitations</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-cinder">
              {data.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </PageShell>
  );
}
