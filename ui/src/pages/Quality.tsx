import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchQuality, runAction } from "@/lib/api";
import { formatCost, formatDecimal, formatNumber, formatPercent } from "@/lib/format";
import { useSelectedTimeRange } from "@/hooks/useSelectedTimeRange";
import { useToastStore } from "@/state/toast";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame, Chip } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { HorizontalBars, Sparkline } from "@/components/charts";
import { Stat } from "@/components/ui";
import { QualityScoreDetails } from "@/components/quality/QualityScoreDetails";
import type { QualityInvestigation } from "@/lib/types";

export function QualityPage() {
  const { range, rangeKey } = useSelectedTimeRange();
  const showToast = useToastStore((s) => s.show);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["quality", rangeKey],
    queryFn: () => fetchQuality(range),
  });

  const checkMut = useMutation({
    mutationFn: () => runAction("check"),
    onSuccess: (res) => {
      const ok = res.ok && res.result?.passed !== false;
      showToast(ok ? "CI gate passed" : "CI gate failed");
    },
    onError: () => showToast("CI gate check failed"),
  });

  if (isLoading) {
    return (
      <PageShell title="Quality" question="Is the work actually good, and what does success cost?">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell title="Quality" question="Is the work actually good, and what does success cost?">
        <ErrorCard />
      </PageShell>
    );
  }

  const ledger = data.ledger;

  if (data.outcomes.length === 0) {
    return (
      <PageShell title="Quality" question="Is the work actually good, and what does success cost?">
        <EmptyCard
          title="Outcomes not captured yet"
          detail="Outcome rows appear after sync records quality evidence. Configure budgets.min_quality under Settings → Quality; there is no outcomes.enabled switch."
          action={
            <a
              href="/settings?tab=quality"
              className="rounded-sm bg-copper px-3 py-2 font-mono text-xs text-anthracite"
            >
              Open Settings → Quality
            </a>
          }
        />
      </PageShell>
    );
  }

  const cpsSeries = data.cost_per_success
    .map((row) => Number(row.cost_per_success))
    .filter((v) => Number.isFinite(v));
  const qualityTrend = data.trend
    .map((point) => point.quality_mean)
    .filter((value): value is number => value != null);

  return (
    <PageShell title="Quality" question="Is the work actually good, and what does success cost?">
      <div className="space-y-6">
        <section className="card p-5" aria-labelledby="quality-answer">
          <p className="page-kicker">Quality ledger · selected range</p>
          <h2 id="quality-answer" className="font-display text-xl text-bone">
            Process quality vs task evidence
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
            label="Mean process quality"
            value={ledger.quality_mean == null ? "—" : formatDecimal(ledger.quality_mean, 1)}
            detail={`${formatNumber(ledger.scored_sessions)}/${formatNumber(ledger.outcome_sessions)} scored`}
            help={{
              definition: "Weighted process-quality score from success, efficiency, and stability.",
              limitations: "Not a task-outcome label and not human ground truth.",
            }}
          />
          <Stat
            label="Verified completion"
            value={
              ledger.verified_completion_rate == null
                ? "—"
                : formatPercent(ledger.verified_completion_rate * 100)
            }
            detail="Tests run or passing build recorded"
          />
          <Stat
            label="Verification debt"
            value={
              ledger.verification_debt_rate == null
                ? "—"
                : formatPercent(ledger.verification_debt_rate * 100)
            }
            detail="Success labels without test/build evidence"
          />
          <Stat
            label="Cost per success"
            value={
              ledger.mean_cost_per_success == null ? "—" : formatCost(ledger.mean_cost_per_success)
            }
            detail="Mean across sessions with cost/success"
            estimated
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Stat
            label="Unsupported claims"
            value="Unavailable"
            detail="Needs verification receipts"
            help={{
              definition: "Share of completion claims without linked evidence.",
              limitations: "Claim-to-evidence support lands with verification receipts.",
            }}
          />
          <Stat
            label="Lucky-pass flags"
            value={formatNumber(ledger.lucky_pass_count)}
            detail="High process score with brittle/human-down signals"
          />
          <Stat
            label="Unlucky-fail flags"
            value={formatNumber(ledger.unlucky_fail_count)}
            detail="Low process score with success/human-up signals"
          />
        </div>

        <div className="card p-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h3 className="font-display text-sm text-bone">CI quality gate</h3>
              <p className="mt-1 text-sm text-cinder">
                Run the local check action against current workspace outcomes.
              </p>
            </div>
            <button
              type="button"
              className="rounded-sm bg-copper px-3 py-2 font-mono text-xs text-anthracite disabled:opacity-50"
              disabled={checkMut.isPending}
              onClick={() => checkMut.mutate()}
            >
              {checkMut.isPending ? "Running…" : "Run check"}
            </button>
          </div>
        </div>

        {data.trend.length > 0 ? (
          <ChartFrame
            title="Quality over time"
            subtitle="Process score with human-label overlays and debt/verified rates"
            summary={`${data.trend.length} daily points; human labels shown as overlay counts.`}
            rows={data.trend}
            columns={[
              { key: "day", label: "Day", value: (row) => row.day },
              {
                key: "q",
                label: "Quality mean",
                numeric: true,
                value: (row) =>
                  row.quality_mean == null ? "—" : formatDecimal(row.quality_mean, 1),
              },
              {
                key: "verified",
                label: "Verified",
                numeric: true,
                value: (row) =>
                  row.verified_rate == null ? "—" : formatPercent(row.verified_rate * 100),
              },
              {
                key: "debt",
                label: "Debt",
                numeric: true,
                value: (row) => (row.debt_rate == null ? "—" : formatPercent(row.debt_rate * 100)),
              },
              {
                key: "human",
                label: "Human ±",
                numeric: true,
                value: (row) => `${row.human_up}↑ / ${row.human_down}↓`,
              },
            ]}
          >
            {qualityTrend.length > 1 ? (
              <Sparkline data={qualityTrend} width={560} height={64} />
            ) : (
              <p className="text-sm text-cinder">
                Need more daily quality samples for a trend sparkline.
              </p>
            )}
          </ChartFrame>
        ) : null}

        {data.histogram.length > 0 ? (
          <ChartFrame
            title="Process-quality histogram"
            subtitle="Score distribution 0–100 (process, not outcome)"
            summary={`${data.histogram.length} quality-score buckets across scored sessions.`}
            rows={data.histogram}
            columns={[
              { key: "bucket", label: "Score bucket", value: (row) => row.bucket },
              { key: "count", label: "Sessions", numeric: true, value: (row) => row.count },
            ]}
          >
            <HorizontalBars
              items={data.histogram.map((bucket) => ({
                label: bucket.bucket,
                value: bucket.count,
              }))}
              width={480}
            />
          </ChartFrame>
        ) : null}

        {data.components.length > 0 ? (
          <ChartFrame
            title="Component breakdown"
            subtitle="Mean component × recorded weight across scored sessions"
            summary={`${data.components.length} components; weights are means of stored per-session weights.`}
            rows={data.components}
            columns={[
              { key: "name", label: "Component", value: (row) => row.name.replaceAll("_", " ") },
              {
                key: "mean",
                label: "Mean",
                numeric: true,
                value: (row) => formatPercent(row.mean * 100),
              },
              {
                key: "weight",
                label: "Weight",
                numeric: true,
                value: (row) => formatPercent(row.weight * 100),
              },
              {
                key: "n",
                label: "n",
                numeric: true,
                value: (row) => formatNumber(row.samples),
              },
            ]}
          >
            <HorizontalBars
              items={data.components.map((component) => ({
                label: component.name.replaceAll("_", " "),
                value: component.mean * component.weight * 100,
              }))}
              width={480}
            />
          </ChartFrame>
        ) : null}

        {cpsSeries.length > 1 ? (
          <ChartFrame
            title="Cost per success"
            subtitle="Trend over sessions with cost/success recorded"
            summary={`${cpsSeries.length} scored sessions; latest ${
              cpsSeries.at(-1) == null ? "unavailable" : formatCost(cpsSeries.at(-1) as number)
            }.`}
            rows={cpsSeries.map((value, index) => ({ index: index + 1, value }))}
            columns={[
              { key: "index", label: "Session order", numeric: true, value: (row) => row.index },
              {
                key: "value",
                label: "Cost per success",
                numeric: true,
                value: (row) => formatCost(row.value),
              },
            ]}
          >
            <Sparkline data={cpsSeries} width={480} height={64} />
          </ChartFrame>
        ) : null}

        <CalibrationCard
          coveragePct={data.calibration.coverage_pct}
          humanLabeled={data.calibration.human_labeled}
          agreements={data.calibration.human_agreements}
          agreementRate={data.calibration.human_agreement_rate}
          limitation={data.calibration.limitation}
        />

        <InvestigationsTable investigations={data.investigations} />

        <div className="card overflow-hidden">
          <div className="border-b border-quartz-vein px-4 py-3">
            <h3 className="font-display text-sm text-bone">Recent outcomes</h3>
            <p className="mt-1 text-xs text-cinder">
              Process score, verification state, human label, and cost/success.
            </p>
          </div>
          <table className="w-full text-left text-sm">
            <caption className="sr-only">
              Recent outcome rows with process and verification fields
            </caption>
            <thead className="font-mono text-[10px] uppercase tracking-wide text-cinder">
              <tr>
                <th className="px-4 py-2">Session</th>
                <th className="px-4 py-2">Process score</th>
                <th className="px-4 py-2">Verification</th>
                <th className="px-4 py-2">Human</th>
                <th className="px-4 py-2">Cost/success</th>
              </tr>
            </thead>
            <tbody>
              {data.outcomes.slice(0, 20).map((o) => (
                <tr key={String(o.trace_id)} className="border-t border-quartz-vein/50">
                  <td className="px-4 py-2">
                    <Link
                      to={`/sessions/${String(o.trace_id)}`}
                      className="font-mono text-xs text-copper hover:underline"
                    >
                      {String(o.trace_id).slice(0, 10)}…
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-xs text-bone">
                    {o.quality_score != null ? (
                      <QualityScoreDetails
                        score={Number(o.quality_score)}
                        components={o.quality_components}
                        weights={o.quality_weights}
                      />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <Chip
                      label={o.verification_state}
                      tone={verificationTone(o.verification_state)}
                    />
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-cinder">
                    {o.human_label ?? "—"}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-bone">
                    {o.cost_per_success != null ? formatCost(Number(o.cost_per_success)) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <section className="card p-4" aria-label="Quality limitations">
          <h2 className="font-display text-base text-bone">Interpretation limits</h2>
          <ul className="mt-2 space-y-1 text-xs leading-5 text-cinder">
            {data.limitations.map((limitation) => (
              <li key={limitation}>• {limitation}</li>
            ))}
          </ul>
        </section>
      </div>
    </PageShell>
  );
}

function CalibrationCard({
  coveragePct,
  humanLabeled,
  agreements,
  agreementRate,
  limitation,
}: {
  coveragePct: number;
  humanLabeled: number;
  agreements: number;
  agreementRate: number | null;
  limitation: string;
}) {
  return (
    <section className="card p-4" aria-labelledby="quality-calibration-heading">
      <h2 id="quality-calibration-heading" className="font-display text-base text-bone">
        Calibration and coverage
      </h2>
      <dl className="mt-3 grid gap-3 sm:grid-cols-3">
        <div>
          <dt className="font-mono text-[10px] uppercase text-cinder">Score coverage</dt>
          <dd className="mt-1 font-display text-xl text-bone">{formatPercent(coveragePct)}</dd>
        </div>
        <div>
          <dt className="font-mono text-[10px] uppercase text-cinder">Human labeled</dt>
          <dd className="mt-1 font-display text-xl text-bone">{formatNumber(humanLabeled)}</dd>
        </div>
        <div>
          <dt className="font-mono text-[10px] uppercase text-cinder">Label agreement</dt>
          <dd className="mt-1 font-display text-xl text-bone">
            {agreementRate == null
              ? "—"
              : `${formatPercent(agreementRate * 100)} (${formatNumber(agreements)})`}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-xs text-cinder">{limitation}</p>
    </section>
  );
}

function InvestigationsTable({ investigations }: { investigations: QualityInvestigation[] }) {
  if (investigations.length === 0) {
    return null;
  }
  return (
    <section className="card overflow-hidden" aria-labelledby="quality-investigations-heading">
      <div className="border-b border-quartz-vein px-4 py-3">
        <h2 id="quality-investigations-heading" className="font-display text-base text-bone">
          Lucky-pass / unlucky-fail investigations
        </h2>
        <p className="mt-1 text-xs text-cinder">
          Descriptive heuristics where process quality and outcome/human signals diverge.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <caption className="sr-only">Investigation rows with evidence session links</caption>
          <thead className="bg-slate font-mono text-[10px] uppercase text-cinder">
            <tr>
              <th scope="col" className="px-3 py-2 text-left">
                Kind
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Session
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Score
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Outcome / human
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Reason
              </th>
            </tr>
          </thead>
          <tbody>
            {investigations.map((item) => (
              <tr key={`${item.kind}-${item.trace_id}`} className="border-t border-quartz-vein">
                <td className="px-3 py-2">
                  <Chip
                    label={item.kind.replaceAll("_", " ")}
                    tone={item.kind === "lucky_pass" ? "ochre" : "cinnabar"}
                  />
                </td>
                <td className="px-3 py-2">
                  <Link to={`/sessions/${item.trace_id}`} className="font-mono text-xs text-copper">
                    {item.trace_id.slice(0, 12)}…
                  </Link>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {item.quality_score == null ? "—" : formatDecimal(item.quality_score, 1)}
                </td>
                <td className="px-3 py-2 text-xs text-cinder">
                  {[item.outcome_label ?? "—", item.human_label ?? "unlabeled"].join(" · ")}
                </td>
                <td className="px-3 py-2 text-xs text-cinder">{item.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function verificationTone(
  state: string,
): "default" | "copper" | "patina" | "cinnabar" | "malachite" | "ochre" | "estimated" {
  switch (state) {
    case "verified":
      return "malachite";
    case "failed":
      return "cinnabar";
    case "debt":
      return "ochre";
    case "unverified":
      return "estimated";
    default:
      return "default";
  }
}
