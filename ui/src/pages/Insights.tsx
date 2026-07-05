import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { fetchInsights, runAction } from "@/lib/api";
import type { InsightLifecycle, InsightRow } from "@/lib/types";
import { PageShell } from "@/components/common/PageShell";
import { InsightCard } from "@/components/insights/InsightCard";
import { useToastStore } from "@/state/toast";

const GROUPS: { state: InsightLifecycle; label: string }[] = [
  { state: "new", label: "New" },
  { state: "ack", label: "Acknowledged" },
  { state: "fixed", label: "Fixed" },
  { state: "regressed", label: "Regressed" },
];

export function InsightsPage() {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const showToast = useToastStore((s) => s.show);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["insights"],
    queryFn: () => fetchInsights(),
  });

  const ackMutation = useMutation({
    mutationFn: (insight: InsightRow) =>
      runAction("insight_set_state", { insight_id: insight.insight_id, state: "ack" }),
    onMutate: async (insight) => {
      await queryClient.cancelQueries({ queryKey: ["insights"] });
      const prev = queryClient.getQueryData<{ insights: InsightRow[] }>(["insights"]);
      queryClient.setQueryData(["insights"], {
        insights: (prev?.insights ?? []).map((i) =>
          i.insight_id === insight.insight_id ? { ...i, state: "ack" as const } : i,
        ),
        total: prev?.insights.length ?? 0,
      });
      return { prev, insight };
    },
    onError: (_err, _insight, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(["insights"], ctx.prev);
    },
    onSuccess: (_res, _insight, ctx) => {
      showToast("Insight acknowledged", () => {
        if (ctx?.insight) {
          runAction("insight_set_state", {
            insight_id: ctx.insight.insight_id,
            state: "new",
          }).then(() => queryClient.invalidateQueries({ queryKey: ["insights"] }));
        }
      });
      queryClient.invalidateQueries({ queryKey: ["insights"] });
    },
  });

  const insights = data?.insights ?? [];
  const filtered = useMemo(
    () =>
      severityFilter
        ? insights.filter((i) => i.severity === severityFilter)
        : insights,
    [insights, severityFilter],
  );
  const severities = useMemo(
    () => [...new Set(insights.map((i) => i.severity))],
    [insights],
  );

  if (isLoading) {
    return (
      <PageShell title="Insights" question="What should I fix, and is it worth it?">
        <div className="card h-48 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError) {
    return (
      <PageShell title="Insights" question="What should I fix, and is it worth it?">
        <div className="card p-6 text-cinnabar">Failed to load insights.</div>
      </PageShell>
    );
  }

  return (
    <PageShell title="Insights" question="What should I fix, and is it worth it?">
      {insights.length === 0 ? (
        <div className="card empty-state">
          <h2>No insights yet</h2>
          <p className="mt-2 text-sm">Sync more sessions, then run detectors via cairn optimize.</p>
          <p className="mt-2 text-sm text-cinder">
            Insights surface waste patterns, drift, and optimization opportunities automatically.
          </p>
        </div>
      ) : (
        <div className="space-y-8">
          {severities.length > 1 ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className={`rounded-chip border px-2 py-1 font-mono text-[10px] ${
                  !severityFilter ? "border-copper text-copper" : "border-quartz-vein text-cinder"
                }`}
                onClick={() => setSeverityFilter(null)}
              >
                all
              </button>
              {severities.map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`rounded-chip border px-2 py-1 font-mono text-[10px] ${
                    severityFilter === s ? "border-copper text-copper" : "border-quartz-vein text-cinder"
                  }`}
                  onClick={() => setSeverityFilter(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          ) : null}
          {GROUPS.map((group) => {
            const items = filtered.filter((i) => i.state === group.state);
            if (items.length === 0) return null;
            return (
              <section key={group.state}>
                <h2 className="mb-3 font-mono text-[11px] uppercase tracking-wide text-cinder">
                  {group.label} ({items.length})
                </h2>
                <div className="space-y-3">
                  {items.map((insight) => (
                    <InsightCard
                      key={insight.insight_id}
                      insight={insight}
                      expanded={expanded === insight.insight_id}
                      onToggle={() =>
                        setExpanded(expanded === insight.insight_id ? null : insight.insight_id)
                      }
                      onAck={(row) => ackMutation.mutate(row)}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </PageShell>
  );
}
