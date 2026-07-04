import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchBehavior, timeRangeDays } from "@/lib/api";
import { useUiStore } from "@/state/ui";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";

export function BehaviorPage() {
  const timeRange = useUiStore((s) => s.timeRange);
  const days = timeRangeDays(timeRange);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["behavior", days],
    queryFn: () => fetchBehavior(days),
  });

  if (isLoading) {
    return (
      <PageShell title="Behavior" question="Has my agent changed?">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell title="Behavior" question="Has my agent changed?">
        <ErrorCard />
      </PageShell>
    );
  }

  const sessionCount = data.series.length;
  const drifting = data.drift.length > 0;

  if (sessionCount < 10) {
    return (
      <PageShell title="Behavior" question="Has my agent changed?">
        <EmptyCard
          title="Fingerprinting needs ~10 sessions"
          detail={`Have ${sessionCount} fingerprinted sessions in this window.`}
          action={
            <Link to="/sessions" className="font-mono text-sm text-copper hover:underline">
              View sessions →
            </Link>
          }
        />
      </PageShell>
    );
  }

  return (
    <PageShell title="Behavior" question="Has my agent changed?">
      <div className="space-y-6">
        <div className={`card p-4 ${drifting ? "border-l-2 border-cinnabar" : ""}`}>
          <p className="display text-lg text-bone">
            {drifting
              ? `Drift detected: ${data.drift.length} event(s) in the last ${days} days.`
              : `No drift — behavior within baseline for ${days} days.`}
          </p>
        </div>

        <ChartFrame title="Fingerprint sessions" subtitle={`${sessionCount} sessions fingerprinted`}>
          <ul className="max-h-64 space-y-1 overflow-auto font-mono text-xs">
            {data.series.slice(0, 50).map((row) => (
              <li key={String(row.trace_id)} className="flex justify-between text-cinder">
                <Link
                  to={`/sessions/${String(row.trace_id)}`}
                  className="truncate text-bone hover:text-copper"
                >
                  {String(row.trace_id).slice(0, 12)}…
                </Link>
                <span>{String(row.ts ?? "").slice(0, 10)}</span>
              </li>
            ))}
          </ul>
        </ChartFrame>

        {data.radar ? (
          <ChartFrame title="Baseline radar" subtitle="Current vs baseline fingerprint">
            <dl className="grid gap-2 sm:grid-cols-2 font-mono text-xs text-cinder">
              {Object.entries(data.radar)
                .filter(([k]) => !k.endsWith("_json"))
                .slice(0, 8)
                .map(([key, value]) => (
                  <div key={key} className="flex justify-between border-b border-quartz-vein/40 py-1">
                    <dt>{key}</dt>
                    <dd className="text-bone">{String(value)}</dd>
                  </div>
                ))}
            </dl>
          </ChartFrame>
        ) : null}

        {data.data_notes.length > 0 ? (
          <div className="card p-4 text-sm text-cinder">
            {data.data_notes.map((n, i) => (
              <p key={i}>{n.message}</p>
            ))}
          </div>
        ) : null}
      </div>
    </PageShell>
  );
}
