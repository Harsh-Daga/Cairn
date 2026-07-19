import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchRegions, fetchWaste } from "@/lib/api";
import { formatCost, formatNumber, formatPercent, formatTokens } from "@/lib/format";
import { useSelectedTimeRange } from "@/hooks/useSelectedTimeRange";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { HorizontalBars, StackedArea } from "@/components/charts";
import { Stat } from "@/components/ui";
import type { RegionsAnalyticsResponse } from "@/lib/types";

const REGION_LABELS: Record<string, string> = {
  system: "System prompt",
  tool_schema: "Tool schemas",
  tool_result: "Tool results",
  retrieved: "Retrieved context",
  user: "User messages",
  history: "Conversation history",
  assistant_history: "Conversation history",
};

export function ContextPage() {
  const { range, rangeKey } = useSelectedTimeRange();
  const regionsQ = useQuery({
    queryKey: ["regions", rangeKey],
    queryFn: () => fetchRegions(range),
  });
  const wasteQ = useQuery({
    queryKey: ["waste", rangeKey],
    queryFn: () => fetchWaste(range),
  });

  if (regionsQ.isLoading || wasteQ.isLoading) {
    return (
      <PageShell title="Context" question="Where your tokens go, repeat, and remain measurable.">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (regionsQ.isError || wasteQ.isError || !regionsQ.data) {
    return (
      <PageShell title="Context" question="Where your tokens go, repeat, and remain measurable.">
        <ErrorCard />
      </PageShell>
    );
  }

  const data = regionsQ.data;
  const ledger = data.ledger;
  const regions = data.regions;
  const waste = wasteQ.data;
  const trend = trendRows(data);
  const regionKeys = [...new Set(data.trend.map((point) => point.region))];
  const cacheCoverage =
    data.coverage.reduce((sum, row) => sum + row.cache_measured_sessions, 0) /
    Math.max(
      1,
      data.coverage.reduce((sum, row) => sum + row.sessions, 0),
    );

  return (
    <PageShell title="Context" question="Where your tokens go, repeat, and remain measurable.">
      <div className="space-y-6">
        <section className="card p-5" aria-labelledby="context-answer">
          <p className="page-kicker">Context ledger · selected range</p>
          <h2 id="context-answer" className="font-display text-xl text-bone">
            Where your tokens go
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
            label="Tool results"
            value={formatPercent(ledger.tool_result_share)}
            detail={`${formatTokens(
              regions.find((region) => region.region === "tool_result")?.tokens ?? 0,
            )} mapped tokens`}
            help={{
              definition: "Share of mapped region tokens classified as tool results.",
              calculation: "tool_result tokens ÷ mapped region tokens",
              limitations: "Mapped rows accumulate across turns and are not a partition of input.",
            }}
          />
          <Stat
            label="Estimated re-billed"
            value={formatTokens(ledger.estimated_rebilled_tokens)}
            detail={
              ledger.repetition_intensity != null
                ? `${formatPercent(ledger.repetition_intensity * 100)} of mapped tokens`
                : "Same-hash repetition after one copy"
            }
            estimated
            help={{
              definition: "Repeated same-hash region tokens after keeping one copy.",
              calculation: "sum(tokens) − max(tokens) per content hash and region",
              limitations: "Not proof the tokens were avoidable or unpaid by a provider cache.",
            }}
          />
          <Stat
            label="Tool-schema overhead"
            value={formatTokens(ledger.schema_overhead_tokens)}
            detail={`${formatCost(data.schema_overhead_cost, 4)} recorded or estimated`}
            help={{
              definition: "Tokens mapped into the tool_schema region.",
              source: "context_regions rows for tool_schema",
            }}
          />
          <Stat
            label="Cache field coverage"
            value={formatPercent(cacheCoverage * 100)}
            detail={
              ledger.cache_savings_available
                ? "Savings fields available"
                : "Field presence only; no savings claim"
            }
            help={{
              definition: "Share of sessions that recorded cache read/creation counters.",
              limitations: "Provider cache pricing and eligibility are not inferred.",
            }}
          />
        </div>

        {regions.length > 0 ? (
          <ChartFrame
            title="Region composition and trend"
            subtitle="Timezone-aware daily mapped tokens"
            summary={`${formatTokens(ledger.mapped_region_tokens)} mapped tokens across ${trend.length} represented days.`}
            rows={regions}
            columns={[
              {
                key: "region",
                label: "Region",
                value: (row) => REGION_LABELS[row.region] ?? row.region,
              },
              {
                key: "tokens",
                label: "Tokens",
                value: (row) => formatNumber(row.tokens),
                numeric: true,
              },
              {
                key: "cost",
                label: "Cost",
                value: (row) => formatCost(row.cost, 4),
                numeric: true,
              },
            ]}
          >
            {trend.length > 1 ? (
              <StackedArea data={trend} keys={regionKeys} xKey="day" width={720} height={220} />
            ) : (
              <HorizontalBars
                items={regions.map((region) => ({
                  label: REGION_LABELS[region.region] ?? region.region,
                  value: region.tokens,
                }))}
                width={520}
              />
            )}
          </ChartFrame>
        ) : (
          <EmptyCard
            title="No mapped context regions"
            detail="Review adapter coverage below. Cairn does not infer missing regions from total input tokens."
          />
        )}

        <RebilledBlocks blocks={data.rebilled_blocks} />
        <CacheLedger data={data} />

        <div className="grid gap-6 xl:grid-cols-2">
          <AgentComparison data={data} />
          <CoverageTable data={data} />
        </div>

        <ChartFrame
          title="Waste ledger"
          subtitle="Detected categories; uncategorized estimates remain explicit"
          summary={`${formatTokens(waste?.total_waste_tokens ?? 0)} tokens were flagged across ${(waste?.categories ?? []).length} categories.`}
          rows={waste?.categories ?? []}
          columns={[
            {
              key: "category",
              label: "Category",
              value: (row) => row.category.replace(/_/g, " "),
            },
            {
              key: "tokens",
              label: "Tokens",
              value: (row) => formatNumber(row.tokens),
              numeric: true,
            },
          ]}
        >
          {(waste?.categories ?? []).length > 0 ? (
            <HorizontalBars
              items={(waste?.categories ?? []).map((category) => ({
                label: category.category.replace(/_/g, " "),
                value: category.tokens,
              }))}
              width={520}
            />
          ) : (
            <p className="text-sm text-cinder">No waste categories recorded in this range.</p>
          )}
        </ChartFrame>

        <section className="card p-4" aria-label="Context limitations">
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


function trendRows(data: RegionsAnalyticsResponse): Record<string, number | string>[] {
  const rows = new Map<string, Record<string, number | string>>();
  for (const point of data.trend) {
    const row = rows.get(point.day) ?? { day: point.day.slice(5) };
    row[point.region] = point.tokens;
    rows.set(point.day, row);
  }
  return [...rows.values()];
}

function RebilledBlocks({ blocks }: { blocks: RegionsAnalyticsResponse["rebilled_blocks"] }) {
  return (
    <section className="card overflow-hidden" aria-labelledby="rebilled-heading">
      <div className="border-b border-quartz-vein px-4 py-3">
        <h2 id="rebilled-heading" className="font-display text-base text-bone">
          Top re-billed blocks
        </h2>
        <p className="mt-1 text-xs text-cinder">
          Ranked same-hash repetition with one exact occurrence and a bounded suggested fix.
        </p>
      </div>
      {blocks.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <caption className="sr-only">
              Top re-billed context blocks with estimated repetition and evidence links
            </caption>
            <thead className="bg-slate font-mono text-[10px] uppercase text-cinder">
              <tr>
                <th scope="col" className="px-3 py-2 text-left">
                  Block / region
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  Occurrences
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  Est. re-billed
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  Cost
                </th>
                <th scope="col" className="px-3 py-2 text-left">
                  Suggested fix / evidence
                </th>
              </tr>
            </thead>
            <tbody>
              {blocks.map((block) => (
                <tr
                  key={`${block.block_id}-${block.region}`}
                  className="border-t border-quartz-vein/50"
                >
                  <td className="px-3 py-3">
                    <div className="font-mono text-xs text-bone">{block.block_id}</div>
                    <div className="text-xs text-cinder">
                      {REGION_LABELS[block.region] ?? block.region}
                    </div>
                  </td>
                  <td className="px-3 py-3 text-right font-mono text-xs">{block.occurrences}</td>
                  <td className="px-3 py-3 text-right font-mono text-xs">
                    <span className="estimated-chip">
                      {formatTokens(block.estimated_rebilled_tokens)}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-right font-mono text-xs">
                    {formatCost(block.cost, 4)}
                  </td>
                  <td className="max-w-md px-3 py-3 text-xs text-cinder">
                    <p>{block.suggested_fix}</p>
                    <Link
                      to={`/sessions/${encodeURIComponent(block.evidence.trace_id)}?span=${encodeURIComponent(block.evidence.span_id)}`}
                      className="mt-1 inline-flex min-h-11 items-center font-mono text-[10px] text-copper"
                    >
                      {block.evidence.label}
                    </Link>
                    <p className="mt-1 text-[10px]">{block.limitation}</p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="p-4 text-sm text-cinder">
          No repeated retained content hashes were recorded in this range.
        </p>
      )}
    </section>
  );
}

function CacheLedger({ data }: { data: RegionsAnalyticsResponse }) {
  const rows = data.cache_trend.map((point) => ({
    day: point.day.slice(5),
    input: point.input_tokens,
    read: point.cache_read_tokens,
    creation: point.cache_creation_tokens,
  }));
  return (
    <ChartFrame
      title="Cache-hit trend"
      subtitle="Recorded cache counters and field coverage"
      summary={
        rows.length > 0
          ? `${rows.length} daily points. Estimated dollar savings are unavailable because provider semantics are not established.`
          : "No cache counters were recorded."
      }
      rows={data.cache_trend}
      columns={[
        { key: "day", label: "Day", value: (row) => row.day },
        {
          key: "read",
          label: "Cache read",
          value: (row) => formatNumber(row.cache_read_tokens),
          numeric: true,
        },
        {
          key: "hit",
          label: "Hit ratio",
          value: (row) =>
            row.hit_ratio == null ? "Unavailable" : formatPercent(row.hit_ratio * 100),
          numeric: true,
        },
        {
          key: "coverage",
          label: "Measured sessions",
          value: (row) => `${row.measured_sessions}/${row.total_sessions}`,
          numeric: true,
        },
        {
          key: "savings",
          label: "Estimated savings",
          value: () => "Unavailable",
        },
      ]}
    >
      {rows.length > 0 ? (
        <StackedArea
          data={rows}
          keys={["input", "read", "creation"]}
          xKey="day"
          width={720}
          height={220}
        />
      ) : (
        <p className="text-sm text-cinder">No cache field coverage in this range.</p>
      )}
    </ChartFrame>
  );
}

function AgentComparison({ data }: { data: RegionsAnalyticsResponse }) {
  return (
    <section className="card overflow-hidden" aria-labelledby="agent-context-heading">
      <div className="border-b border-quartz-vein px-4 py-3">
        <h2 id="agent-context-heading" className="font-display text-base text-bone">
          Per-agent context
        </h2>
      </div>
      {data.agents.length > 0 ? (
        <table className="w-full text-sm">
          <caption className="sr-only">Per-agent mapped context tokens and top region</caption>
          <thead className="bg-slate font-mono text-[10px] uppercase text-cinder">
            <tr>
              <th scope="col" className="px-3 py-2 text-left">
                Agent
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Sessions
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Tokens
              </th>
              <th scope="col" className="px-3 py-2 text-left">
                Top region
              </th>
            </tr>
          </thead>
          <tbody>
            {data.agents.map((agent) => (
              <tr key={agent.agent_id} className="border-t border-quartz-vein/50">
                <td className="px-3 py-2">
                  <Link
                    to={`/sessions?agent=${encodeURIComponent(agent.agent_id)}`}
                    className="inline-flex min-h-11 items-center font-mono text-xs text-copper"
                  >
                    {agent.agent_id}
                  </Link>
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">{agent.sessions}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {formatTokens(agent.tokens)}
                </td>
                <td className="px-3 py-2 text-xs text-cinder">
                  {agent.top_region ? (REGION_LABELS[agent.top_region] ?? agent.top_region) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="p-4 text-sm text-cinder">No agent-attributed region evidence.</p>
      )}
    </section>
  );
}

function CoverageTable({ data }: { data: RegionsAnalyticsResponse }) {
  return (
    <section className="card overflow-hidden" aria-labelledby="coverage-heading">
      <div className="border-b border-quartz-vein px-4 py-3">
        <h2 id="coverage-heading" className="font-display text-base text-bone">
          Adapter data quality / coverage
        </h2>
      </div>
      {data.coverage.length > 0 ? (
        <table className="w-full text-sm">
          <caption className="sr-only">
            Adapter region and cache field coverage with dropped events
          </caption>
          <thead className="bg-slate font-mono text-[10px] uppercase text-cinder">
            <tr>
              <th scope="col" className="px-3 py-2 text-left">
                Source
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Region
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Cache
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Dropped
              </th>
            </tr>
          </thead>
          <tbody>
            {data.coverage.map((coverage) => (
              <tr key={coverage.source} className="border-t border-quartz-vein/50">
                <td className="px-3 py-2 font-mono text-xs text-bone">{coverage.source}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {formatPercent(coverage.region_coverage_pct)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {formatPercent(coverage.cache_coverage_pct)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {coverage.dropped_events}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="p-4 text-sm text-cinder">No sessions in the selected range.</p>
      )}
    </section>
  );
}
