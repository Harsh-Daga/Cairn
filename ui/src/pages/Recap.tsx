import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Chip } from "@/components/common/Chip";
import { ErrorCard } from "@/components/common/DataViews";
import { PageShell } from "@/components/common/PageShell";
import { fetchRecap } from "@/lib/api";
import { formatCost, formatDecimal, formatPercent, formatRelative } from "@/lib/format";

export function RecapPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["recap"],
    queryFn: fetchRecap,
  });

  if (isLoading) {
    return (
      <PageShell title="Weekly recap" question="What changed in the last seven local days?">
        <div className="card h-48 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }
  if (isError || !data) {
    return (
      <PageShell title="Weekly recap" question="What changed in the last seven local days?">
        <ErrorCard />
      </PageShell>
    );
  }

  const trend = data.quality_trend;
  const cps = data.cost_per_success_trend;
  const action = data.recommended_action;

  return (
    <PageShell title="Weekly recap" question="What changed in the last seven local days?">
      <div className="space-y-4">
        <section className="card p-6">
          <p className="page-kicker">
            Rolling {data.period_days}d · {data.timezone} · {data.period_kind} · generated locally
          </p>
          <p className="mt-1 font-mono text-[10px] text-cinder">
            {data.period_start.slice(0, 19)} → {data.period_end.slice(0, 19)}
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            <RecapMetric label="Spend" value={formatCost(data.money.total_spend_usd)} />
            <RecapMetric
              label="Avoidable spend"
              value={formatCost(data.money.wasted_spend_usd)}
              detail={`${formatPercent(data.money.wasted_spend_pct)} · estimated`}
            />
            <RecapMetric
              label="Quality"
              value={trend.current_mean == null ? "Unavailable" : formatDecimal(trend.current_mean)}
              detail={`${trend.current_sessions} scored sessions`}
            />
            <RecapMetric
              label="Quality change"
              value={
                trend.delta == null
                  ? "No prior baseline"
                  : `${trend.delta >= 0 ? "+" : ""}${formatDecimal(trend.delta)}`
              }
              detail={`${trend.previous_sessions} prior scored sessions`}
            />
            <RecapMetric
              label="Cost / success"
              value={cps.current_mean == null ? "Unavailable" : formatCost(cps.current_mean)}
              detail={`${cps.current_sessions} sessions with CPS`}
            />
            <RecapMetric
              label="CPS change"
              value={
                cps.delta == null
                  ? "No prior baseline"
                  : `${cps.delta >= 0 ? "+" : ""}${formatCost(cps.delta)}`
              }
              detail={`${cps.previous_sessions} prior CPS sessions`}
            />
          </div>
        </section>

        {action ? (
          <section className="card p-6">
            <h2 className="font-display text-base text-bone">Recommended action</h2>
            <p className="mt-2 text-sm text-cinder">{action.reason}</p>
            <Link
              to={action.href}
              className="mt-4 inline-flex rounded-sm bg-copper px-4 py-2 text-sm font-semibold text-anthracite"
            >
              {action.label}
            </Link>
          </section>
        ) : null}

        <section className="card p-6">
          <h2 className="font-display text-base text-bone">Top causes</h2>
          {data.money.top_causes.length > 0 ? (
            <ol className="mt-3 space-y-3">
              {data.money.top_causes.map((cause, index) => (
                <li key={cause.category} className="rounded-sm border border-quartz-vein p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-ash">0{index + 1}</span>
                    <Chip label="estimated impact" tone="estimated" />
                    <span className="font-mono text-sm text-ochre">
                      {formatCost(cause.estimated_savings_usd)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-bone">{cause.cause}</p>
                  <p className="mt-1 text-xs text-patina">Fix: {cause.fix}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-3 text-sm text-cinder">
              No priced waste cause is available in this recap window.
            </p>
          )}
        </section>

        {(data.best_session || data.worst_session) && (
          <section className="card p-6">
            <h2 className="font-display text-base text-bone">Session extremes (by cost)</h2>
            <ul className="mt-3 space-y-2">
              {data.best_session ? (
                <li className="rounded-sm border border-quartz-vein p-3">
                  <Chip label="lowest cost" tone="malachite" />
                  <Link
                    to={data.best_session.href}
                    className="mt-2 block font-mono text-sm text-copper hover:underline"
                  >
                    {data.best_session.title}
                  </Link>
                  <p className="mt-1 text-xs text-cinder">{formatCost(data.best_session.value)}</p>
                </li>
              ) : null}
              {data.worst_session ? (
                <li className="rounded-sm border border-quartz-vein p-3">
                  <Chip label="highest cost" tone="copper" />
                  <Link
                    to={data.worst_session.href}
                    className="mt-2 block font-mono text-sm text-copper hover:underline"
                  >
                    {data.worst_session.title}
                  </Link>
                  <p className="mt-1 text-xs text-cinder">{formatCost(data.worst_session.value)}</p>
                </li>
              ) : null}
            </ul>
          </section>
        )}

        <section className="card p-6">
          <h2 className="font-display text-base text-bone">Experiment verdicts</h2>
          {data.experiment_verdicts.length > 0 ? (
            <ul className="mt-3 space-y-2">
              {data.experiment_verdicts.map((verdict) => (
                <li
                  key={verdict.experiment_id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-sm border border-quartz-vein p-3"
                >
                  <span className="font-mono text-xs text-bone">
                    {verdict.experiment_id.slice(0, 12)}…
                  </span>
                  <Chip label={verdict.verdict} tone="patina" />
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-cinder">
              No experiment reached a verdict in this seven-day window.
            </p>
          )}
        </section>

        {data.decayed_rules.length > 0 ? (
          <section className="card p-6">
            <h2 className="font-display text-base text-bone">Decayed rules</h2>
            <ul className="mt-3 space-y-2">
              {data.decayed_rules.map((rule) => (
                <li key={rule.experiment_id} className="rounded-sm border border-quartz-vein p-3">
                  <div className="flex flex-wrap gap-2">
                    <Chip label={rule.decay_state} tone="copper" />
                    {rule.target_file ? <Chip label={rule.target_file} /> : null}
                  </div>
                  {rule.plain_verdict ? (
                    <p className="mt-2 text-sm text-cinder">{rule.plain_verdict}</p>
                  ) : null}
                  <Link
                    to={rule.href}
                    className="mt-2 inline-flex font-mono text-xs text-copper hover:underline"
                  >
                    Open in Optimize
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {data.guard_events.length > 0 ? (
          <section className="card p-6">
            <h2 className="font-display text-base text-bone">Guard events</h2>
            <ul className="mt-3 space-y-2">
              {data.guard_events.map((event) => (
                <li key={event.event_id} className="rounded-sm border border-quartz-vein p-3">
                  <div className="flex flex-wrap gap-2">
                    <Chip label={event.event_kind} />
                    <Chip label={event.path_rel} />
                  </div>
                  <p className="mt-2 font-mono text-[10px] text-cinder">
                    {formatRelative(event.occurred_at)}
                  </p>
                  <Link
                    to={event.href}
                    className="mt-2 inline-flex font-mono text-xs text-copper hover:underline"
                  >
                    Open in Guard
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {data.limitations.length > 0 ? (
          <section className="card p-4" aria-label="Recap limitations">
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

function RecapMetric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-sm border border-quartz-vein p-4">
      <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">{label}</p>
      <p className="mt-2 font-display text-xl text-bone">{value}</p>
      {detail ? <p className="mt-1 text-xs text-cinder">{detail}</p> : null}
    </div>
  );
}
