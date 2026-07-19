import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchAgents } from "@/lib/api";
import { formatCost, formatNumber, formatPercent, formatTokens } from "@/lib/format";
import { useSelectedTimeRange } from "@/hooks/useSelectedTimeRange";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame, Chip } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { HandoffDag } from "@/components/agents/HandoffDag";
import { HorizontalBars, Sparkline } from "@/components/charts";
import { Stat } from "@/components/ui";
import type { AgentAggregate, AgentsResponse } from "@/lib/types";

export function AgentsPage() {
  const { range, rangeKey } = useSelectedTimeRange();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["agents", rangeKey],
    queryFn: () => fetchAgents(range),
  });

  if (isLoading) {
    return (
      <PageShell
        title="Agents"
        question="Understand ownership, collaboration, cost, and handoffs across your agent fleet."
      >
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell
        title="Agents"
        question="Understand ownership, collaboration, cost, and handoffs across your agent fleet."
      >
        <ErrorCard />
      </PageShell>
    );
  }

  const ledger = data.ledger;
  const handoffs = data.handoff_matrix;

  if (data.agents.length === 0) {
    return (
      <PageShell
        title="Agents"
        question="Understand ownership, collaboration, cost, and handoffs across your agent fleet."
      >
        <EmptyCard
          title="No agent activity"
          detail="Run cairn sync to ingest multi-agent sessions."
        />
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Agents"
      question="Understand ownership, collaboration, cost, and handoffs across your agent fleet."
    >
      <div className="space-y-6">
        <section className="card p-5" aria-labelledby="agents-answer">
          <p className="page-kicker">Agent ledger · selected range</p>
          <h2 id="agents-answer" className="font-display text-xl text-bone">
            Who did the work
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
            label="Agents"
            value={formatNumber(ledger.agent_count)}
            detail={`n=${ledger.sample_size} sessions`}
          />
          <Stat
            label="Multi-agent sessions"
            value={formatNumber(ledger.multi_agent_sessions)}
            detail={`${ledger.handoffs} handoff links`}
          />
          <Stat
            label="Top spend"
            value={formatCost(data.agents[0]?.cost ?? 0)}
            detail={data.agents[0]?.agent_id ?? "default"}
          />
          <Stat
            label="Fingerprint samples"
            value={formatNumber(
              data.agents.reduce((sum, agent) => sum + agent.fingerprint_samples, 0),
            )}
            detail="Mean vectors when available"
            help={{
              definition: "Count of fingerprint vectors averaged into thumbnails.",
              limitations: "Missing fingerprints stay unavailable rather than invented.",
            }}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.agents.slice(0, 12).map((agent, index) => (
            <AgentCard key={`${agent.agent_id}-${agent.actor_id}-${index}`} agent={agent} />
          ))}
        </div>

        <ChartFrame
          title="Attributed spend by agent"
          subtitle="Token-share cost attribution within sessions"
          summary={`${data.agents.length} agents. Sample sizes are shown on each card.`}
          rows={data.agents}
          columns={[
            {
              key: "agent",
              label: "Agent",
              value: (row) => row.agent_id ?? "default",
            },
            {
              key: "n",
              label: "n",
              value: (row) => formatNumber(row.sample_size),
              numeric: true,
            },
            {
              key: "cost",
              label: "Cost",
              value: (row) => formatCost(row.cost),
              numeric: true,
            },
            {
              key: "waste",
              label: "Waste tokens",
              value: (row) => formatTokens(row.waste_tokens),
              numeric: true,
            },
            {
              key: "quality",
              label: "Quality mean",
              value: (row) =>
                row.quality_mean == null
                  ? "Unavailable"
                  : `${row.quality_mean} (n=${row.quality_samples})`,
            },
          ]}
        >
          <HorizontalBars
            items={data.agents.slice(0, 12).map((agent) => ({
              label: agent.agent_id ?? "default",
              value: agent.cost,
            }))}
            width={560}
          />
        </ChartFrame>

        <section className="card overflow-hidden" aria-labelledby="handoff-heading">
          <div className="border-b border-quartz-vein px-4 py-3">
            <h2 id="handoff-heading" className="font-display text-base text-bone">
              Handoff map
            </h2>
            <p className="font-mono text-[10px] text-cinder">
              {handoffs.length} handoff{handoffs.length === 1 ? "" : "s"} observed
            </p>
          </div>
          <div className="overflow-x-auto p-4">
            <HandoffDag handoffs={handoffs} />
          </div>
          <HandoffTable data={data} />
        </section>

        <CoverageTable data={data} />

        <section className="card p-4" aria-label="Agents limitations">
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

function AgentCard({ agent }: { agent: AgentAggregate }) {
  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Chip label={agent.agent_id ?? "default"} tone="patina" />
        {agent.actor_name ? (
          <Chip label={agent.actor_name} />
        ) : agent.actor_id ? (
          <Chip label={agent.actor_id.slice(0, 8)} />
        ) : null}
        <span className="font-mono text-[10px] text-cinder">n={agent.sample_size}</span>
      </div>
      {agent.fingerprint_thumbnail && agent.fingerprint_thumbnail.length > 0 ? (
        <div className="mt-3" aria-label="Fingerprint thumbnail">
          <Sparkline data={agent.fingerprint_thumbnail} width={180} height={36} />
          <p className="mt-1 font-mono text-[10px] text-cinder">
            fingerprint mean · {agent.fingerprint_samples} samples
          </p>
        </div>
      ) : (
        <p className="mt-3 font-mono text-[10px] text-cinder">Fingerprint unavailable</p>
      )}
      <dl className="mt-3 space-y-1 font-mono text-xs text-cinder">
        <div className="flex justify-between">
          <dt>Tokens</dt>
          <dd className="text-bone">{formatTokens(agent.input_tokens + agent.output_tokens)}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Spend</dt>
          <dd className="text-bone">{formatCost(agent.cost)}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Waste</dt>
          <dd className="text-bone">{formatTokens(agent.waste_tokens)}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Quality</dt>
          <dd className="text-bone">
            {agent.quality_mean == null
              ? "Unavailable"
              : `${agent.quality_mean} (n=${agent.quality_samples})`}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Models</dt>
          <dd className="truncate text-right text-bone">
            {agent.models.length > 0 ? agent.models.join(", ") : "—"}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt>Errors</dt>
          <dd className="text-bone">{agent.error_sessions}</dd>
        </div>
      </dl>
      <Link
        to={`/sessions?agent=${encodeURIComponent(agent.agent_id ?? "")}`}
        className="mt-3 inline-flex min-h-11 items-center text-xs text-copper hover:underline"
      >
        Filter sessions →
      </Link>
    </div>
  );
}

function HandoffTable({ data }: { data: AgentsResponse }) {
  if (data.handoff_matrix.length === 0) {
    return null;
  }
  return (
    <div className="border-t border-quartz-vein">
      <table className="w-full text-sm">
        <caption className="sr-only">Accessible handoff table alternative to the graph</caption>
        <thead className="bg-slate font-mono text-[10px] uppercase text-cinder">
          <tr>
            <th scope="col" className="px-3 py-2 text-left">
              From
            </th>
            <th scope="col" className="px-3 py-2 text-left">
              To
            </th>
            <th scope="col" className="px-3 py-2 text-left">
              Link
            </th>
          </tr>
        </thead>
        <tbody>
          {data.handoff_matrix.map((row) => (
            <tr
              key={`${row.from_span_id}-${row.to_span_id}-${row.link_type}`}
              className="border-t border-quartz-vein/50"
            >
              <td className="px-3 py-2 font-mono text-xs text-bone">
                {row.from_agent ?? row.from_span_id}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-bone">
                {row.to_agent ?? row.to_span_id}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-cinder">{row.link_type}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CoverageTable({ data }: { data: AgentsResponse }) {
  return (
    <section className="card overflow-hidden" aria-labelledby="agent-coverage-heading">
      <div className="border-b border-quartz-vein px-4 py-3">
        <h2 id="agent-coverage-heading" className="font-display text-base text-bone">
          Adapter parse health / coverage
        </h2>
      </div>
      {data.coverage.length > 0 ? (
        <table className="w-full text-sm">
          <caption className="sr-only">
            Per-adapter session counts and parse-health counters
          </caption>
          <thead className="bg-slate font-mono text-[10px] uppercase text-cinder">
            <tr>
              <th scope="col" className="px-3 py-2 text-left">
                Source
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Sessions
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Parse success
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Degraded
              </th>
              <th scope="col" className="px-3 py-2 text-right">
                Skipped
              </th>
            </tr>
          </thead>
          <tbody>
            {data.coverage.map((row) => (
              <tr key={row.source} className="border-t border-quartz-vein/50">
                <td className="px-3 py-2 font-mono text-xs text-bone">{row.source}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{row.sessions}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">
                  {row.parse_success_pct == null
                    ? "Unavailable"
                    : formatPercent(row.parse_success_pct)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-xs">{row.degraded}</td>
                <td className="px-3 py-2 text-right font-mono text-xs">{row.skipped}</td>
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

