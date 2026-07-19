import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchTools } from "@/lib/api";
import { formatNumber, formatPercent, formatTokens } from "@/lib/format";
import { useSelectedTimeRange } from "@/hooks/useSelectedTimeRange";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { HorizontalBars } from "@/components/charts";
import { DataTable, Stat } from "@/components/ui";
import type { ToolsAnalyticsResponse } from "@/lib/types";

const FAMILY_LABELS: Record<string, string> = {
  builtin: "Built-in",
  mcp: "MCP",
  shell: "Shell",
  unknown: "Unknown",
};

export function ToolsPage() {
  const { range, rangeKey } = useSelectedTimeRange();
  const toolsQ = useQuery({
    queryKey: ["tools", rangeKey],
    queryFn: () => fetchTools(range),
  });

  if (toolsQ.isLoading) {
    return (
      <PageShell title="Tools" question="Which tools run, fail, retry, and tax the schema?">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (toolsQ.isError || !toolsQ.data) {
    return (
      <PageShell title="Tools" question="Which tools run, fail, retry, and tax the schema?">
        <ErrorCard />
      </PageShell>
    );
  }

  const data = toolsQ.data;
  const ledger = data.ledger;

  return (
    <PageShell title="Tools" question="Which tools run, fail, retry, and tax the schema?">
      <div className="space-y-6">
        <section className="card p-5" aria-labelledby="tools-answer">
          <p className="page-kicker">Tool ledger · selected range</p>
          <h2 id="tools-answer" className="font-display text-xl text-bone">
            Tool usage under evidence
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
            label="Invocations"
            value={formatNumber(ledger.invocations)}
            detail={`${ledger.distinct_tools} normalized tools`}
          />
          <Stat
            label="Error rate"
            value={formatPercent(ledger.error_rate)}
            detail={`${ledger.sessions_with_tools}/${ledger.sessions_total} sessions with tools`}
          />
          <Stat
            label="Retry-linked"
            value={formatPercent(ledger.retry_rate)}
            detail="Waste categories tied to repetition"
            help={{
              definition: "Share of tool_call spans with repetition waste categories.",
              limitations: "Not every logical retry policy is observed as a waste category.",
            }}
          />
          <Stat
            label="Schema overhead"
            value={formatTokens(ledger.schema_overhead_tokens)}
            detail={
              ledger.schema_tax_estimated
                ? "Mapped tool_schema tokens; not per-tool allocated"
                : "No tool_schema region tokens in range"
            }
            estimated={ledger.schema_tax_estimated}
            help={{
              definition: "Workspace tool_schema region tokens from Context mapping.",
              limitations: "Not proof a specific MCP tool is unused.",
            }}
          />
        </div>

        {data.tools.length > 0 ? (
          <ChartFrame
            title="Tool volume"
            subtitle="Normalized identity; aliases collapse into one row"
            summary={`${data.tools.length} tools. Cost share is token-proportional among tool calls.`}
            rows={data.tools}
            columns={[
              {
                key: "tool",
                label: "Tool",
                value: (row) => row.display_name,
              },
              {
                key: "family",
                label: "Family",
                value: (row) => FAMILY_LABELS[row.family] ?? row.family,
              },
              {
                key: "invocations",
                label: "Calls",
                value: (row) => formatNumber(row.invocations),
                numeric: true,
              },
              {
                key: "error",
                label: "Error %",
                value: (row) => formatPercent(row.error_rate),
                numeric: true,
              },
              {
                key: "cost",
                label: "Est. cost share",
                value: (row) => formatPercent(row.estimated_cost_share),
                numeric: true,
              },
            ]}
          >
            <HorizontalBars
              items={data.tools.slice(0, 12).map((tool) => ({
                label: tool.display_name,
                value: tool.invocations,
              }))}
              width={560}
            />
          </ChartFrame>
        ) : (
          <EmptyCard
            title="No tool_call spans"
            detail="Adapters may not have extracted tools for sessions in this range."
          />
        )}

        <ToolTable data={data} />
        <FailureSamples data={data} />
        <CoverageTable data={data} />

        <section className="card p-4" aria-label="Tools limitations">
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

function ToolTable({ data }: { data: ToolsAnalyticsResponse }) {
  return (
    <div className="space-y-3" aria-labelledby="tools-table-heading">
      <div>
        <h2 id="tools-table-heading" className="font-display text-base text-bone">
          Normalized tools
        </h2>
        <p className="mt-1 text-xs text-cinder">
          Success/error/retry rates, latency, result tokens, and evidence for the worst session.
        </p>
      </div>
      <DataTable
        label="Normalized tools"
        rows={data.tools}
        rowKey={(tool) => tool.tool_id}
        empty={<p className="text-sm text-cinder">No normalized tools in this range.</p>}
        columns={[
          {
            key: "tool",
            header: "Tool",
            cell: (tool) => (
              <div>
                <div className="font-mono text-xs text-bone">{tool.display_name}</div>
                <div className="text-[10px] text-cinder">{tool.tool_id}</div>
              </div>
            ),
          },
          {
            key: "family",
            header: "Family",
            cell: (tool) => FAMILY_LABELS[tool.family] ?? tool.family,
          },
          {
            key: "calls",
            header: "Calls",
            numeric: true,
            cell: (tool) => tool.invocations,
          },
          {
            key: "error",
            header: "Error %",
            numeric: true,
            cell: (tool) => formatPercent(tool.error_rate),
          },
          {
            key: "retry",
            header: "Retry %",
            numeric: true,
            cell: (tool) => formatPercent(tool.retry_rate),
          },
          {
            key: "latency",
            header: "p50 / p95 ms",
            numeric: true,
            cell: (tool) =>
              tool.median_latency_ms == null
                ? "—"
                : `${Math.round(tool.median_latency_ms)} / ${
                    tool.p95_latency_ms == null ? "—" : Math.round(tool.p95_latency_ms)
                  }`,
          },
          {
            key: "tokens",
            header: "Result tokens",
            numeric: true,
            cell: (tool) => formatTokens(tool.result_tokens),
          },
          {
            key: "evidence",
            header: "Evidence",
            cell: (tool) =>
              tool.worst_session ? (
                <Link
                  to={`/sessions/${encodeURIComponent(tool.worst_session.trace_id)}?span=${encodeURIComponent(tool.worst_session.span_id)}`}
                  className="inline-flex min-h-11 items-center font-mono text-[10px] text-copper"
                >
                  {tool.worst_session.label}
                </Link>
              ) : (
                <span className="text-cinder">—</span>
              ),
          },
        ]}
      />
    </div>
  );
}

function FailureSamples({ data }: { data: ToolsAnalyticsResponse }) {
  return (
    <section className="card overflow-hidden" aria-labelledby="tool-failures-heading">
      <div className="border-b border-quartz-vein px-4 py-3">
        <h2 id="tool-failures-heading" className="font-display text-base text-bone">
          Failure samples
        </h2>
      </div>
      {data.failures.length > 0 ? (
        <ul className="divide-y divide-quartz-vein/50">
          {data.failures.map((failure) => (
            <li
              key={`${failure.evidence.trace_id}-${failure.evidence.span_id}`}
              className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
            >
              <div>
                <p className="font-mono text-xs text-bone">{failure.display_name}</p>
                <p className="mt-1 text-xs text-cinder">{failure.detail}</p>
              </div>
              <Link
                to={`/sessions/${encodeURIComponent(failure.evidence.trace_id)}?span=${encodeURIComponent(failure.evidence.span_id)}`}
                className="inline-flex min-h-11 items-center font-mono text-[10px] text-copper"
              >
                {failure.evidence.label}
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="p-4 text-sm text-cinder">No tool_call errors recorded in this range.</p>
      )}
    </section>
  );
}

function CoverageTable({ data }: { data: ToolsAnalyticsResponse }) {
  return (
    <div className="space-y-3" aria-labelledby="tool-coverage-heading">
      <h2 id="tool-coverage-heading" className="font-display text-base text-bone">
        Adapter tool coverage
      </h2>
      <DataTable
        label="Adapter tool coverage"
        rows={data.coverage}
        rowKey={(row) => row.source}
        empty={<p className="text-sm text-cinder">No sessions in the selected range.</p>}
        columns={[
          {
            key: "source",
            header: "Source",
            cell: (row) => <span className="font-mono text-xs text-bone">{row.source}</span>,
          },
          {
            key: "coverage",
            header: "Tool sessions",
            numeric: true,
            cell: (row) => formatPercent(row.tool_coverage_pct),
          },
          {
            key: "distinct",
            header: "Distinct",
            numeric: true,
            cell: (row) => row.distinct_tools,
          },
          {
            key: "mapped",
            header: "Mapped",
            numeric: true,
            cell: (row) => row.mapped_tools,
          },
        ]}
      />
    </div>
  );
}
