import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchAgents, timeRangeDays } from "@/lib/api";
import { formatCost, formatTokens } from "@/lib/format";
import { useUiStore } from "@/state/ui";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { HandoffDag } from "@/components/agents/HandoffDag";

export function AgentsPage() {
  const timeRange = useUiStore((s) => s.timeRange);
  const days = timeRangeDays(timeRange);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["agents", days],
    queryFn: () => fetchAgents(days),
  });

  if (isLoading) {
    return (
      <PageShell title="Agents" question="Understand ownership, collaboration, cost, and handoffs across your agent fleet.">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell title="Agents" question="Understand ownership, collaboration, cost, and handoffs across your agent fleet.">
        <ErrorCard />
      </PageShell>
    );
  }

  const uniqueAgents = new Set(data.agents.map((a) => a.agent_id ?? "default")).size;
  const handoffs = data.handoff_matrix;

  if (data.agents.length === 0) {
    return (
      <PageShell title="Agents" question="Understand ownership, collaboration, cost, and handoffs across your agent fleet.">
        <EmptyCard
          title="No agent activity"
          detail="Run cairn sync to ingest multi-agent sessions."
        />
      </PageShell>
    );
  }

  return (
    <PageShell title="Agents" question="Understand ownership, collaboration, cost, and handoffs across your agent fleet.">
      <div className="space-y-6">
        {uniqueAgents <= 1 ? (
          <div className="card p-4 text-sm text-cinder">
            All sessions in this window are single-agent. Multi-agent handoffs appear here
            automatically when subagents or handoff links are detected.
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.agents.slice(0, 12).map((agent, i) => (
            <div key={`${agent.agent_id}-${agent.actor_id}-${i}`} className="card p-4">
              <div className="flex items-center gap-2">
                <Chip label={agent.agent_id ?? "default"} tone="patina" />
                {agent.actor_name ? (
                  <Chip label={agent.actor_name} />
                ) : agent.actor_id ? (
                  <Chip label={agent.actor_id.slice(0, 8)} />
                ) : null}
              </div>
              <dl className="mt-3 space-y-1 font-mono text-xs text-cinder">
                <div className="flex justify-between">
                  <dt>Sessions</dt>
                  <dd className="text-bone">{agent.traces}</dd>
                </div>
                <div className="flex justify-between">
                  <dt>Tokens</dt>
                  <dd className="text-bone">
                    {formatTokens(agent.input_tokens + agent.output_tokens)}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt>Spend</dt>
                  <dd className="text-bone">{formatCost(agent.cost)}</dd>
                </div>
              </dl>
              <Link
                to={`/sessions?agent=${encodeURIComponent(agent.agent_id ?? "")}`}
                className="mt-3 inline-block text-xs text-copper hover:underline"
              >
                Filter sessions →
              </Link>
            </div>
          ))}
        </div>

        <div className="card overflow-hidden">
          <div className="border-b border-quartz-vein px-4 py-3">
            <h3 className="font-display text-sm text-bone">Handoff map</h3>
            <p className="font-mono text-[10px] text-cinder">
              {handoffs.length} handoff{handoffs.length === 1 ? "" : "s"} observed
            </p>
          </div>
          <div className="overflow-x-auto p-4">
            <HandoffDag handoffs={handoffs} />
          </div>
        </div>
      </div>
    </PageShell>
  );
}
