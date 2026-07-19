import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchCompare } from "@/lib/api";
import { formatCost, formatDecimal, formatNumber, formatPercent, formatTokens } from "@/lib/format";
import { useSelectedTimeRange } from "@/hooks/useSelectedTimeRange";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame, Chip } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { IntervalPlot } from "@/components/charts";
import { Stat } from "@/components/ui";
import type { CompareCell, ComparePairwise } from "@/lib/types";

export function ComparePage() {
  const { range, rangeKey } = useSelectedTimeRange();
  const compareQ = useQuery({
    queryKey: ["compare", rangeKey],
    queryFn: () => fetchCompare(range),
  });

  if (compareQ.isLoading) {
    return (
      <PageShell
        title="Compare"
        question="Which agent performs best for this repository and task difficulty?"
      >
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (compareQ.isError || !compareQ.data) {
    return (
      <PageShell
        title="Compare"
        question="Which agent performs best for this repository and task difficulty?"
      >
        <ErrorCard />
      </PageShell>
    );
  }

  const data = compareQ.data;
  const ledger = data.ledger;
  const intervalPoints = data.cells
    .filter((cell) => cell.cost_per_session.value != null && cell.cost_per_session.sufficient)
    .slice(0, 12)
    .map((cell) => ({
      label: `${cell.agent_id} · ${cell.difficulty_bucket}`,
      value: cell.cost_per_session.value ?? 0,
      low: cell.cost_per_session.ci_low ?? cell.cost_per_session.value ?? 0,
      high: cell.cost_per_session.ci_high ?? cell.cost_per_session.value ?? 0,
    }));

  return (
    <PageShell
      title="Compare"
      question="Which agent performs best for this repository and task difficulty?"
    >
      <div className="space-y-6">
        <section className="card p-5" aria-labelledby="compare-answer">
          <p className="page-kicker">Compare ledger · selected range</p>
          <h2 id="compare-answer" className="font-display text-xl text-bone">
            Difficulty-aware agent performance
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-cinder">{ledger.conclusion}</p>
          <p className="mt-3 text-xs text-cinder">{ledger.limitation}</p>
          {ledger.declared_winner ? (
            <p className="mt-3 font-mono text-xs text-copper">
              Declared winner (spend): {ledger.declared_winner}
            </p>
          ) : (
            <p className="mt-3 font-mono text-xs text-cinder">No leaderboard winner declared</p>
          )}
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
            label="Difficulty buckets"
            value={formatNumber(ledger.buckets_with_evidence)}
            detail="With at least one session"
          />
          <Stat
            label="Agent×bucket cells"
            value={formatNumber(ledger.cells_total)}
            detail={`${ledger.cells_sufficient} meet n≥${ledger.min_sample}`}
          />
          <Stat
            label="Min sample"
            value={formatNumber(ledger.min_sample)}
            detail="Required before intervals count as sufficient"
            help={{
              definition: "Minimum sessions in an agent×difficulty cell before ranking claims.",
              limitations: "Below this threshold Cairn shows descriptive values only.",
            }}
          />
          <Stat
            label="Confound warnings"
            value={formatNumber(data.confound_warnings.length)}
            detail="Model/source mix across agents"
          />
        </div>

        {data.cells.length === 0 ? (
          <EmptyCard
            title="No comparable sessions"
            detail="Sync sessions with difficulty scores, then reopen Compare."
          />
        ) : (
          <>
            <ChartFrame
              title="Cost per session by difficulty"
              subtitle="Anytime-valid intervals for cells that meet the minimum sample"
              summary={`${intervalPoints.length} sufficient cells plotted; table lists all cells.`}
              rows={data.cells}
              columns={[
                { key: "agent", label: "Agent", value: (row) => row.agent_id },
                { key: "bucket", label: "Difficulty", value: (row) => row.difficulty_bucket },
                {
                  key: "n",
                  label: "n",
                  value: (row) => formatNumber(row.sessions),
                  numeric: true,
                },
                {
                  key: "cost",
                  label: "Cost/session",
                  value: (row) => formatMetric(row.cost_per_session.value, "cost"),
                  numeric: true,
                },
                {
                  key: "verified",
                  label: "Verified success",
                  value: (row) => formatMetric(row.verified_success_rate.value, "rate"),
                  numeric: true,
                },
              ]}
            >
              {intervalPoints.length > 0 ? (
                <IntervalPlot points={intervalPoints} width={560} height={220} />
              ) : (
                <p className="text-sm text-cinder">
                  No cell yet meets n≥{ledger.min_sample} for interval plotting.
                </p>
              )}
            </ChartFrame>

            <CellsTable cells={data.cells} minSample={ledger.min_sample} />
            <PairwiseTable pairs={data.pairwise} />
          </>
        )}

        <section className="card p-4" aria-label="Compare limitations">
          <h2 className="font-display text-base text-bone">Interpretation limits</h2>
          <ul className="mt-2 space-y-1 text-xs leading-5 text-cinder">
            {data.limitations.map((limitation) => (
              <li key={limitation}>• {limitation}</li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-cinder">
            For turn-by-turn session pairs, use{" "}
            <Link to="/sessions" className="text-copper">
              Sessions → Compare selected
            </Link>
            .
          </p>
        </section>
      </div>
    </PageShell>
  );
}

function CellsTable({ cells, minSample }: { cells: CompareCell[]; minSample: number }) {
  return (
    <section className="card overflow-hidden" aria-labelledby="compare-cells-heading">
      <div className="border-b border-quartz-vein px-4 py-3">
        <h2 id="compare-cells-heading" className="font-display text-base text-bone">
          Agent × difficulty cells
        </h2>
        <p className="mt-1 text-xs text-cinder">
          Cost, tokens, quality, waste, retry, verification debt, verified success, and correction
          burden. Cells below n≥{minSample} stay labeled insufficient.
        </p>
      </div>
      <div
        className="overflow-x-auto"
        tabIndex={0}
        role="region"
        aria-label="Scrollable agent difficulty metrics table"
      >
        <table className="w-full min-w-[1100px] text-sm">
          <caption className="sr-only">
            Difficulty-stratified agent metrics with sample sizes and interval sufficiency
          </caption>
          <thead className="bg-slate font-mono text-[10px] uppercase text-cinder">
            <tr>
              <th scope="col" className="px-3 py-2 text-left">
                Agent
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Difficulty
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                n
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Cost/session
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Tokens/session
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Quality
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Waste
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Retry
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Cost/success
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Verified
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Debt
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Correction
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {cells.map((cell) => (
              <tr
                key={`${cell.agent_id}-${cell.difficulty_bucket}`}
                className="border-t border-quartz-vein"
              >
                <td className="px-3 py-2 font-mono text-xs text-bone">{cell.agent_id}</td>
                <td className="px-3 py-2 text-cinder">{cell.difficulty_bucket}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatNumber(cell.sessions)}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMetric(cell.cost_per_session.value, "cost")}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMetric(cell.tokens_per_session.value, "tokens")}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMetric(cell.quality_mean.value, "number")}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMetric(cell.waste_tokens_per_session.value, "tokens")}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMetric(cell.retry_rate.value, "rate")}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMetric(cell.cost_per_success.value, "cost")}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMetric(cell.verified_success_rate.value, "rate")}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMetric(cell.verification_debt_rate.value, "rate")}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMetric(cell.correction_burden_rate.value, "rate")}
                </td>
                <td className="px-3 py-2">
                  <Chip
                    label={cell.cost_per_session.sufficient ? "sufficient" : "insufficient"}
                    tone={cell.cost_per_session.sufficient ? "malachite" : "ochre"}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PairwiseTable({ pairs }: { pairs: ComparePairwise[] }) {
  if (pairs.length === 0) {
    return null;
  }
  return (
    <section className="card overflow-hidden" aria-labelledby="compare-pairwise-heading">
      <div className="border-b border-quartz-vein px-4 py-3">
        <h2 id="compare-pairwise-heading" className="font-display text-base text-bone">
          Pairwise cost/session
        </h2>
        <p className="mt-1 text-xs text-cinder">
          Within each difficulty bucket. Negative delta favors agent A on spend. Confounds block
          winner claims.
        </p>
      </div>
      <div
        className="overflow-x-auto"
        tabIndex={0}
        role="region"
        aria-label="Scrollable pairwise cost comparison table"
      >
        <table className="w-full min-w-[880px] text-sm">
          <caption className="sr-only">
            Pairwise agent cost-per-session comparisons by difficulty
          </caption>
          <thead className="bg-slate font-mono text-[10px] uppercase text-cinder">
            <tr>
              <th scope="col" className="px-3 py-2 text-left">
                Difficulty
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Agent A
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Agent B
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Δ cost
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                nA / nB
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Verdict
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Confounds
              </th>
            </tr>
          </thead>
          <tbody>
            {pairs.map((pair) => (
              <tr
                key={`${pair.difficulty_bucket}-${pair.agent_a}-${pair.agent_b}`}
                className="border-t border-quartz-vein"
              >
                <td className="px-3 py-2 text-cinder">{pair.difficulty_bucket}</td>
                <td className="px-3 py-2 font-mono text-xs text-bone">{pair.agent_a}</td>
                <td className="px-3 py-2 font-mono text-xs text-bone">{pair.agent_b}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {pair.delta == null ? "—" : formatCost(pair.delta)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatNumber(pair.sample_a)} / {formatNumber(pair.sample_b)}
                </td>
                <td className="px-3 py-2">
                  <Chip
                    label={pair.verdict.replaceAll("_", " ")}
                    tone={verdictTone(pair.verdict)}
                  />
                </td>
                <td className="px-3 py-2 text-xs text-cinder">
                  {pair.confound_warnings.length > 0
                    ? pair.confound_warnings.join("; ")
                    : "none recorded"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function formatMetric(
  value: number | null | undefined,
  kind: "cost" | "tokens" | "rate" | "number",
) {
  if (value == null) {
    return "—";
  }
  switch (kind) {
    case "cost":
      return formatCost(value);
    case "tokens":
      return formatTokens(value);
    case "rate":
      return formatPercent(value * 100);
    case "number":
      return formatDecimal(value, 2);
    default: {
      const _exhaustive: never = kind;
      return _exhaustive;
    }
  }
}

function verdictTone(
  verdict: string,
): "default" | "copper" | "patina" | "cinnabar" | "malachite" | "ochre" | "estimated" {
  switch (verdict) {
    case "a_better":
    case "b_better":
      return "malachite";
    case "insufficient":
      return "ochre";
    case "inconclusive":
      return "estimated";
    default:
      return "default";
  }
}
