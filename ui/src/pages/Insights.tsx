import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchInsightEvidence, fetchInsights, runAction } from "@/lib/api";
import type { InsightLifecycle, InsightRow, InsightsResponse } from "@/lib/types";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import { InsightCard } from "@/components/insights/InsightCard";
import { Stat, SidePanel } from "@/components/ui";
import { useToastStore } from "@/state/toast";
import { splitInsights } from "@/lib/insights";
import { formatNumber } from "@/lib/format";

const GROUPS: { state: InsightLifecycle; label: string }[] = [
  { state: "new", label: "New" },
  { state: "ack", label: "Acknowledged" },
  { state: "fixed", label: "Fixed" },
  { state: "regressed", label: "Regressed" },
];

type ViewMode = "list" | "kanban";

export function InsightsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("insight");
  const [severityFilter, setSeverityFilter] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const queryClient = useQueryClient();
  const showToast = useToastStore((s) => s.show);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["insights"],
    queryFn: () => fetchInsights(),
  });

  const evidenceQ = useQuery({
    queryKey: ["evidence", selectedId],
    queryFn: () => fetchInsightEvidence(selectedId!),
    enabled: Boolean(selectedId),
  });

  const ackMutation = useMutation({
    mutationFn: (insight: InsightRow) =>
      runAction("insight_set_state", { insight_id: insight.insight_id, state: "ack" }),
    onMutate: async (insight) => {
      await queryClient.cancelQueries({ queryKey: ["insights"] });
      const prev = queryClient.getQueryData<InsightsResponse>(["insights"]);
      if (prev) {
        queryClient.setQueryData<InsightsResponse>(["insights"], {
          ...prev,
          insights: prev.insights.map((item) =>
            item.insight_id === insight.insight_id ? { ...item, state: "ack" as const } : item,
          ),
        });
      }
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

  const snoozeMutation = useMutation({
    mutationFn: (insight: InsightRow) =>
      runAction("insight_snooze", { insight_id: insight.insight_id, days: 14 }),
    onSuccess: () => {
      showToast("Insight snoozed for 14 days");
      queryClient.invalidateQueries({ queryKey: ["insights"] });
      if (selectedId) {
        setSearchParams({}, { replace: true });
      }
    },
    onError: () => showToast("Snooze failed", undefined, "error"),
  });

  const insights = useMemo(
    () => (data?.insights ?? []).filter((item) => item.state !== "muted"),
    [data?.insights],
  );
  const filtered = useMemo(
    () => (severityFilter ? insights.filter((i) => i.severity === severityFilter) : insights),
    [insights, severityFilter],
  );
  const { recommendations, diagnostics } = splitInsights(filtered);
  const severities = useMemo(() => [...new Set(insights.map((i) => i.severity))], [insights]);
  const selected = insights.find((item) => item.insight_id === selectedId) ?? null;
  const ledger = data?.ledger;

  const selectInsight = (insightId: string | null) => {
    if (!insightId) {
      setSearchParams({}, { replace: true });
      return;
    }
    setSearchParams({ insight: insightId }, { replace: true });
  };

  if (isLoading) {
    return (
      <PageShell
        title="Insights"
        question="Prioritize evidence-backed improvements by severity, impact, and confidence."
      >
        <div className="card h-48 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data || !ledger) {
    return (
      <PageShell
        title="Insights"
        question="Prioritize evidence-backed improvements by severity, impact, and confidence."
      >
        <div className="card p-6 text-cinnabar">Failed to load insights.</div>
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Insights"
      question="Prioritize evidence-backed improvements by severity, impact, and confidence."
    >
      <div className="space-y-6">
        <section className="card p-5" aria-labelledby="insights-answer">
          <p className="page-kicker">Insights ledger · workspace</p>
          <h2 id="insights-answer" className="font-display text-xl text-bone">
            Ranked findings under evidence
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
          <Stat label="Open" value={formatNumber(ledger.open_count)} detail="New, ack, regressed" />
          <Stat
            label="Ranked"
            value={formatNumber(ledger.ranked_count)}
            detail="After duplicate suppression"
          />
          <Stat
            label="Snoozed"
            value={formatNumber(ledger.snoozed_count)}
            detail="Hidden for up to 14 days"
          />
          <Stat
            label="Suppressed dupes"
            value={formatNumber(ledger.suppressed_duplicates)}
            detail="Same primary evidence trace"
          />
        </div>

        {insights.length === 0 ? (
          <div className="card empty-state">
            <h2>No insights yet</h2>
            <p className="mt-2 text-sm">
              Sync more sessions, then run detectors via cairn optimize.
            </p>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-2" role="group" aria-label="Severity filter">
                <FilterChip
                  active={!severityFilter}
                  label="all"
                  onClick={() => setSeverityFilter(null)}
                />
                {severities.map((severity) => (
                  <FilterChip
                    key={severity}
                    active={severityFilter === severity}
                    label={severity}
                    onClick={() => setSeverityFilter(severity)}
                  />
                ))}
              </div>
              <div className="flex gap-2" role="group" aria-label="Insights view mode">
                <FilterChip
                  active={viewMode === "list"}
                  label="list"
                  onClick={() => setViewMode("list")}
                />
                <FilterChip
                  active={viewMode === "kanban"}
                  label="kanban"
                  onClick={() => setViewMode("kanban")}
                />
              </div>
            </div>

            {viewMode === "kanban" ? (
              <div className="grid gap-4 lg:grid-cols-4">
                {GROUPS.map((group) => {
                  const items = recommendations.filter((item) => item.state === group.state);
                  return (
                    <section key={group.state} className="card p-3" aria-label={group.label}>
                      <h2 className="mb-3 font-mono text-[11px] uppercase tracking-wide text-cinder">
                        {group.label} ({items.length})
                      </h2>
                      <div className="space-y-3">
                        {items.map((insight) => (
                          <InsightCard
                            key={insight.insight_id}
                            insight={insight}
                            selected={selectedId === insight.insight_id}
                            onSelect={() => selectInsight(insight.insight_id)}
                            onAck={(row) => ackMutation.mutate(row)}
                            onSnooze={(row) => snoozeMutation.mutate(row)}
                          />
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>
            ) : (
              <div className="space-y-8">
                {GROUPS.map((group) => {
                  const items = recommendations.filter((item) => item.state === group.state);
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
                            selected={selectedId === insight.insight_id}
                            onSelect={() => selectInsight(insight.insight_id)}
                            onAck={(row) => ackMutation.mutate(row)}
                            onSnooze={(row) => snoozeMutation.mutate(row)}
                          />
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>
            )}

            {diagnostics.length > 0 ? (
              <section>
                <h2 className="mb-1 font-display text-lg text-bone">Diagnostics</h2>
                <p className="mb-3 text-xs text-cinder">
                  Supporting evidence that needs investigation before Cairn can recommend a change.
                </p>
                <div className="space-y-3">
                  {diagnostics.map((insight) => (
                    <InsightCard
                      key={insight.insight_id}
                      insight={insight}
                      selected={selectedId === insight.insight_id}
                      onSelect={() => selectInsight(insight.insight_id)}
                      onAck={(row) => ackMutation.mutate(row)}
                      onSnooze={(row) => snoozeMutation.mutate(row)}
                    />
                  ))}
                </div>
              </section>
            ) : null}
          </>
        )}

        <section className="card p-4" aria-label="Insights limitations">
          <h2 className="font-display text-base text-bone">Interpretation limits</h2>
          <ul className="mt-2 space-y-1 text-xs leading-5 text-cinder">
            {data.limitations.map((limitation) => (
              <li key={limitation}>• {limitation}</li>
            ))}
          </ul>
        </section>
      </div>

      <SidePanel
        open={Boolean(selected)}
        title={selected?.title ?? "Insight evidence"}
        onClose={() => selectInsight(null)}
      >
        {selected ? (
          <div className="space-y-4 text-sm">
            <p className="text-cinder">{selected.body}</p>
            <div className="flex flex-wrap gap-2">
              <Chip label={selected.severity} />
              <Chip label={`rank ${selected.rank_score.toFixed(2)}`} tone="estimated" />
              <Chip label={selected.confidence} tone="patina" />
            </div>
            <div className="rounded-sm border border-patina/30 bg-patina/5 p-3">
              <p className="font-mono text-[10px] uppercase tracking-wide text-patina">
                {selected.fix.kind} fix
              </p>
              <p className="mt-2 text-bone">{selected.fix.value}</p>
              {selected.savings_estimate == null ? (
                <p className="mt-2 text-xs text-cinder">{selected.savings_unavailable_reason}</p>
              ) : null}
              <button
                type="button"
                className="mt-3 rounded-sm border border-patina/50 px-2.5 py-1.5 font-mono text-[10px] text-patina hover:bg-patina/10"
                onClick={() => {
                  navigator.clipboard.writeText(selected.fix.value).then(
                    () => showToast("Fix copied"),
                    () => showToast("Copy failed", undefined, "error"),
                  );
                }}
              >
                Copy fix
              </button>
            </div>
            {evidenceQ.data ? (
              <div>
                <h3 className="font-mono text-[10px] uppercase text-cinder">Evidence</h3>
                <p className="mt-2 font-mono text-xs text-bone">
                  producer {evidenceQ.data.producer} · {evidenceQ.data.trace_ids.length} trace(s)
                </p>
                <ul className="mt-2 space-y-1">
                  {evidenceQ.data.trace_ids.slice(0, 8).map((traceId) => (
                    <li key={traceId}>
                      <Link to={`/sessions/${traceId}`} className="font-mono text-xs text-copper">
                        {traceId.slice(0, 12)}…
                      </Link>
                    </li>
                  ))}
                </ul>
                {evidenceQ.data.spans.length > 0 ? (
                  <ul className="mt-3 space-y-1 font-mono text-[10px] text-cinder">
                    {evidenceQ.data.spans.slice(0, 8).map((span) => (
                      <li key={span.span_id}>
                        {span.kind} · {span.name ?? span.span_id.slice(0, 8)}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : (
              <p className="text-xs text-cinder">Loading evidence…</p>
            )}
            {(selected.state === "new" || selected.state === "regressed") && (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="rounded-sm border border-copper/50 px-3 py-2 font-mono text-xs text-copper"
                  onClick={() => ackMutation.mutate(selected)}
                >
                  Ack
                </button>
                <button
                  type="button"
                  className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-cinder"
                  onClick={() => snoozeMutation.mutate(selected)}
                >
                  Snooze 14d
                </button>
              </div>
            )}
          </div>
        ) : null}
      </SidePanel>
    </PageShell>
  );
}


function FilterChip({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`rounded-chip border px-2 py-1 font-mono text-[10px] ${
        active ? "border-copper text-copper" : "border-quartz-vein text-cinder"
      }`}
      aria-pressed={active}
      onClick={onClick}
    >
      {label}
    </button>
  );
}
