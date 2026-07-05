import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchBehavior, timeRangeDays } from "@/lib/api";
import { useUiStore } from "@/state/ui";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { ControlChart, Radar, Sparkline, type RadarPoint } from "@/components/charts";

const FINGERPRINT_AXES = ["read_write", "explore", "retry", "entropy", "turns"] as const;

function vectorNorm(vector: unknown): number {
  if (!Array.isArray(vector) || vector.length === 0) return 0;
  return Math.sqrt(vector.reduce((sum: number, v) => sum + Number(v) ** 2, 0));
}

function ewma(values: number[], alpha = 0.3): number[] {
  if (values.length === 0) return [];
  const out = [values[0] ?? 0];
  for (let i = 1; i < values.length; i += 1) {
    out.push(alpha * (values[i] ?? 0) + (1 - alpha) * (out[i - 1] ?? 0));
  }
  return out;
}

function radarFromBaseline(radar: Record<string, unknown>): RadarPoint[] {
  const axes = radar.axes;
  if (Array.isArray(axes)) {
    return axes.map((a) => {
      if (typeof a === "object" && a !== null && "axis" in a && "value" in a) {
        return {
          axis: String((a as { axis: unknown }).axis),
          value: Number((a as { value: unknown }).value),
        };
      }
      return { axis: "?", value: 0 };
    });
  }
  const mean = radar.mean_vector;
  if (Array.isArray(mean) && mean.length > 0) {
    return mean.slice(0, 6).map((v, i) => ({
      axis: FINGERPRINT_AXES[i] ?? `d${i}`,
      value: Math.abs(Number(v)),
    }));
  }
  return FINGERPRINT_AXES.map((axis) => ({
    axis,
    value: Math.abs(Number(radar[`${axis}_ratio`] ?? radar[axis] ?? 0)),
  })).filter((p) => p.value > 0);
}

export function BehaviorPage() {
  const timeRange = useUiStore((s) => s.timeRange);
  const days = timeRangeDays(timeRange);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["behavior", days],
    queryFn: () => fetchBehavior(days),
  });

  const metricSeries = useMemo(() => {
    if (!data) return [];
    return data.series.map((row) => vectorNorm(row.vector));
  }, [data]);

  const ewmaSeries = useMemo(() => ewma(metricSeries), [metricSeries]);

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

  const radarPoints = data.radar ? radarFromBaseline(data.radar) : [];

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

        {radarPoints.length >= 3 ? (
          <ChartFrame title="Baseline radar" subtitle="Current vs baseline fingerprint">
            <Radar points={radarPoints} width={280} height={280} />
          </ChartFrame>
        ) : null}

        {metricSeries.length > 2 ? (
          <ChartFrame title="Fingerprint drift" subtitle="Vector norm over sessions">
            <ControlChart data={metricSeries} width={640} height={200} />
          </ChartFrame>
        ) : null}

        {ewmaSeries.length > 1 ? (
          <ChartFrame title="EWMA smoothed" subtitle="Exponentially weighted moving average">
            <Sparkline data={ewmaSeries} width={640} height={64} />
          </ChartFrame>
        ) : null}

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
