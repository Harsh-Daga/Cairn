import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { IntervalPlot } from "@/components/charts";
import { Chip } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame } from "@/components/charts/ChartFrame";
import { Stat } from "@/components/ui";
import { useSelectedTimeRange } from "@/hooks/useSelectedTimeRange";
import { fetchGuard } from "@/lib/api";
import { formatDecimal, formatNumber, formatRelative } from "@/lib/format";
import type { GuardEventRow } from "@/lib/types";


function EventCard({ event, selected }: { event: GuardEventRow; selected: boolean }) {
  const assoc = event.association;
  return (
    <article
      id={`guard-${event.event_id}`}
      className={`card p-4 ${selected ? "ring-1 ring-copper/50" : ""}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Chip label={event.event_kind} tone="copper" />
        <Chip label={event.path_rel} />
        <Chip label={event.git_state} />
        {assoc ? <Chip label={assoc.language.replace(/_/g, " ")} tone="patina" /> : null}
        {assoc ? <Chip label={assoc.verdict} /> : null}
      </div>
      <p className="mt-2 font-mono text-xs text-cinder">
        {formatRelative(event.occurred_at)}
        {event.commit_sha ? ` · ${event.commit_sha.slice(0, 12)}…` : ""}
      </p>
      {event.diff_summary ? (
        <p className="mt-3 text-sm text-bone">{event.diff_summary}</p>
      ) : (
        <p className="mt-3 text-sm text-cinder">No scrubbed diff summary for this event.</p>
      )}
      {event.confound_notes.length > 0 ? (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-cinder">
          {event.confound_notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
      {assoc ? (
        <div className="mt-4 space-y-2">
          <p className="text-sm text-cinder">
            {assoc.language === "unavailable"
              ? assoc.limitation
              : `Cost/session ${assoc.language.replace(/_/g, " ")} this edit: verdict ${assoc.verdict} (pre n=${assoc.pre_n}, post n=${assoc.post_n}).`}
          </p>
          {assoc.effect_estimate != null &&
          assoc.effect_ci_low != null &&
          assoc.effect_ci_high != null ? (
            <ChartFrame
              title="Associated cost shift"
              subtitle="Non-causal interval around the instruction edit"
              summary={`Estimated cost/session shift ${formatDecimal(assoc.effect_estimate, 3)}, interval ${formatDecimal(assoc.effect_ci_low, 3)} to ${formatDecimal(assoc.effect_ci_high, 3)}.`}
              rows={[
                {
                  label: "cost/session",
                  value: assoc.effect_estimate,
                  low: assoc.effect_ci_low,
                  high: assoc.effect_ci_high,
                },
              ]}
              columns={[
                { key: "metric", label: "Metric", value: (row) => row.label },
                {
                  key: "estimate",
                  label: "Estimate",
                  value: (row) => formatDecimal(row.value, 3),
                  numeric: true,
                },
                {
                  key: "low",
                  label: "Low",
                  value: (row) => formatDecimal(row.low, 3),
                  numeric: true,
                },
                {
                  key: "high",
                  label: "High",
                  value: (row) => formatDecimal(row.high, 3),
                  numeric: true,
                },
              ]}
            >
              <IntervalPlot
                points={[
                  {
                    label: "cost",
                    value: assoc.effect_estimate,
                    low: assoc.effect_ci_low,
                    high: assoc.effect_ci_high,
                  },
                ]}
                width={320}
                height={80}
              />
            </ChartFrame>
          ) : null}
          <p className="text-xs text-cinder">{assoc.limitation}</p>
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-3">
        {event.optimize_href ? (
          <Link to={event.optimize_href} className="font-mono text-xs text-copper hover:underline">
            Linked Optimize rule
          </Link>
        ) : null}
        <span className="font-mono text-[10px] text-cinder">{event.event_id.slice(0, 16)}…</span>
      </div>
    </article>
  );
}

export function GuardPage() {
  const [searchParams] = useSearchParams();
  const selected = searchParams.get("event");
  const { range, rangeKey } = useSelectedTimeRange();
  const guardQ = useQuery({
    queryKey: ["guard", rangeKey],
    queryFn: () => fetchGuard(range),
  });

  if (guardQ.isLoading) {
    return (
      <PageShell
        title="Guard"
        question="Which instruction-file edits are associated with later session shifts?"
      >
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (guardQ.isError || !guardQ.data?.ledger) {
    return (
      <PageShell
        title="Guard"
        question="Which instruction-file edits are associated with later session shifts?"
      >
        <ErrorCard />
      </PageShell>
    );
  }

  const { ledger, events, limitations } = guardQ.data;
  const ordered = selected
    ? [
        ...events.filter((event) => event.event_id === selected),
        ...events.filter((event) => event.event_id !== selected),
      ]
    : events;

  return (
    <PageShell
      title="Guard"
      question="Which instruction-file edits are associated with later session shifts?"
    >
      <div className="space-y-6">
        <section className="card p-5" aria-labelledby="guard-answer">
          <p className="page-kicker">Guard ledger · selected range</p>
          <h2 id="guard-answer" className="font-display text-xl text-bone">
            Instruction edits under association, not causation
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
            label="Events"
            value={formatNumber(ledger.event_count)}
            detail="In selected range"
          />
          <Stat
            label="Associated"
            value={formatNumber(ledger.associated_count)}
            detail="With pre/post windows"
            help={{
              definition: "Events with enough sessions to compute a non-causal association.",
              limitations: "Never treated as proof the edit caused the metric shift.",
            }}
          />
          <Stat
            label="Confounded"
            value={formatNumber(ledger.confounded_count)}
            detail="Mix shifted between windows"
          />
          <Stat label="Git state" value={ledger.git_state} detail="Latest scan / workspace state" />
        </div>

        {ordered.length === 0 ? (
          <EmptyCard
            title="No instruction-file events"
            detail="Guard observes AGENTS.md, CLAUDE.md, and .cursor/rules history. No-git and dirty worktrees are reported explicitly."
          />
        ) : (
          <div className="space-y-3">
            {ordered.map((event) => (
              <EventCard
                key={event.event_id}
                event={event}
                selected={selected === event.event_id}
              />
            ))}
          </div>
        )}

        {limitations.length > 0 ? (
          <section className="card p-4" aria-label="Guard limitations">
            <h3 className="font-display text-sm text-bone">Limitations</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-cinder">
              {limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </PageShell>
  );
}
