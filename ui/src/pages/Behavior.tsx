import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchBehavior } from "@/lib/api";
import { useSelectedTimeRange } from "@/hooks/useSelectedTimeRange";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame, Chip } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { ControlChart, Radar, Sparkline, type RadarPoint } from "@/components/charts";
import { Stat } from "@/components/ui";
import type { BehaviorRadar } from "@/lib/generated/api-types";
import { formatDecimal, formatNumber } from "@/lib/format";

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

function radarFromBaseline(radar: BehaviorRadar): RadarPoint[] {
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
  return [];
}

export function BehaviorPage() {
  const { range, rangeKey } = useSelectedTimeRange();
  const [showControl, setShowControl] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["behavior", rangeKey],
    queryFn: () => fetchBehavior(range),
  });

  const metricSeries = useMemo(() => {
    if (!data) return [];
    return data.series.map((row) => vectorNorm(row.vector));
  }, [data]);

  const ewmaSeries = useMemo(() => ewma(metricSeries), [metricSeries]);

  if (isLoading) {
    return (
      <PageShell
        title="Behavior"
        question="Has my agent changed relative to its local fingerprint baseline?"
      >
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell
        title="Behavior"
        question="Has my agent changed relative to its local fingerprint baseline?"
      >
        <ErrorCard />
      </PageShell>
    );
  }

  const ledger = data.ledger;
  const baseline = data.baseline_progress;
  const radarPoints = data.radar ? radarFromBaseline(data.radar) : [];
  const driftedSessions = data.drift.filter((event) => event.trace_id);

  if (data.series.length === 0) {
    return (
      <PageShell
        title="Behavior"
        question="Has my agent changed relative to its local fingerprint baseline?"
      >
        <EmptyCard
          title="No fingerprints yet"
          detail="Run cairn sync so sessions can be fingerprinted for drift detection."
        />
      </PageShell>
    );
  }

  return (
    <PageShell
      title="Behavior"
      question="Has my agent changed relative to its local fingerprint baseline?"
    >
      <div className="space-y-6">
        <section className="card p-5" aria-labelledby="behavior-answer">
          <p className="page-kicker">Behavior ledger · selected range</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h2 id="behavior-answer" className="font-display text-xl text-bone">
              Fingerprint vs baseline
            </h2>
            <Chip label="Experimental" tone="estimated" />
          </div>
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
            label="Fingerprinted"
            value={formatNumber(ledger.fingerprint_sessions)}
            detail="Sessions with vectors in range"
          />
          <Stat
            label="Drift events"
            value={formatNumber(ledger.drift_events)}
            detail={ledger.drift_events > 0 ? "Joint shock and/or gradual" : "None recorded"}
          />
          <Stat
            label="Baseline"
            value={`${ledger.baseline_collected}/${ledger.baseline_required}`}
            detail={ledger.baseline_ready ? "Ready for joint shock" : "Still collecting"}
            help={{
              definition: "Matched project/model sessions required before joint-shock claims.",
              limitations: "Incomplete baselines never imply “no drift.”",
            }}
          />
          <Stat
            label="Primary axis"
            value={ledger.primary_axis ?? "—"}
            detail="Highest absolute mean on reference radar"
          />
        </div>

        {!baseline.ready ? (
          <section className="card p-4" aria-label="Joint-shock baseline progress">
            <div className="flex items-center justify-between font-mono text-[10px] text-cinder">
              <span>{baseline.note}</span>
              <span>EWMA trend remains active</span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-chip bg-granite">
              <div
                className="h-full rounded-chip bg-copper transition-[width]"
                style={{
                  width: `${Math.min(100, (baseline.collected / baseline.required) * 100)}%`,
                }}
              />
            </div>
          </section>
        ) : null}

        {data.drift.length > 0 ? (
          <section className="card overflow-hidden" aria-labelledby="behavior-drift-heading">
            <div className="border-b border-quartz-vein px-4 py-3">
              <h2 id="behavior-drift-heading" className="font-display text-base text-bone">
                Drift evidence
              </h2>
              <p className="mt-1 text-xs text-cinder">
                Kind, date/week, sample size, magnitude, and affected axes. Nearby instruction edits
                are listed on Guard when present for the range.
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[800px] text-sm">
                <caption className="sr-only">Detected drift events with evidence links</caption>
                <thead className="bg-slate font-mono text-[10px] uppercase text-cinder">
                  <tr>
                    <th scope="col" className="px-3 py-2 text-left">
                      Kind
                    </th>
                    <th scope="col" className="px-3 py-2 text-left">
                      When
                    </th>
                    <th scope="col" className="px-3 py-2 text-left">
                      Context
                    </th>
                    <th scope="col" className="px-3 py-2 text-right">
                      n
                    </th>
                    <th scope="col" className="px-3 py-2 text-right">
                      Magnitude
                    </th>
                    <th scope="col" className="px-3 py-2 text-left">
                      Axes
                    </th>
                    <th scope="col" className="px-3 py-2 text-left">
                      Evidence
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.drift.map((event, index) => (
                    <tr
                      key={`${event.kind}-${event.trace_id ?? index}`}
                      className="border-t border-quartz-vein"
                    >
                      <td className="px-3 py-2">
                        <Chip label={event.kind.replaceAll("_", " ")} tone="cinnabar" />
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-cinder">
                        {event.drifted_at ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-xs text-cinder">
                        {[event.project, event.model].filter(Boolean).join(" · ") || "—"}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {formatNumber(event.sample_size)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {event.magnitude == null && event.distance == null
                          ? "—"
                          : formatDecimal(event.magnitude ?? event.distance ?? 0, 2)}
                      </td>
                      <td className="px-3 py-2 text-xs text-cinder">
                        {event.axes?.length
                          ? event.axes
                              .slice(0, 3)
                              .map((axis) => axis.axis_label)
                              .join(", ")
                          : "—"}
                      </td>
                      <td className="px-3 py-2">
                        {event.trace_id ? (
                          <Link
                            to={`/sessions/${event.trace_id}`}
                            className="font-mono text-xs text-copper"
                          >
                            {event.trace_id.slice(0, 12)}…
                          </Link>
                        ) : (
                          <span className="text-xs text-cinder">week-level</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}

        {radarPoints.length >= 3 ? (
          <ChartFrame
            title="Current fingerprint vs baseline axes"
            subtitle="Labeled mean profile for the strongest project/model reference"
            summary={`${radarPoints.length} normalized behavior axes; highest is ${
              [...radarPoints].sort((a, b) => b.value - a.value)[0]?.axis ?? "unavailable"
            }.`}
            rows={radarPoints}
            columns={[
              { key: "axis", label: "Axis", value: (row) => row.axis },
              {
                key: "value",
                label: "Normalized value",
                numeric: true,
                value: (row) => formatDecimal(row.value, 3),
              },
            ]}
          >
            <Radar points={radarPoints} width={280} height={280} />
          </ChartFrame>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn-ghost min-h-11 font-mono text-xs"
            aria-pressed={showControl}
            onClick={() => setShowControl((current) => !current)}
          >
            {showControl ? "Hide control chart" : "Show control chart"}
          </button>
          <span className="text-xs text-cinder">
            EWMA stays visible; control chart is on demand to reduce chart noise.
          </span>
        </div>

        {ewmaSeries.length > 1 ? (
          <ChartFrame
            title="Behavior trend (EWMA)"
            subtitle="Smoothed fingerprint magnitude in chronological session order"
            summary={`${ewmaSeries.length} EWMA values; latest ${
              ewmaSeries.at(-1) == null
                ? "unavailable"
                : formatDecimal(ewmaSeries.at(-1) as number, 3)
            }.`}
            rows={ewmaSeries.map((value, index) => ({ index: index + 1, value }))}
            columns={[
              { key: "index", label: "Session order", numeric: true, value: (row) => row.index },
              {
                key: "value",
                label: "EWMA",
                numeric: true,
                value: (row) => formatDecimal(row.value, 3),
              },
            ]}
          >
            <Sparkline data={ewmaSeries} width={640} height={64} />
          </ChartFrame>
        ) : null}

        {showControl && metricSeries.length > 2 ? (
          <ChartFrame
            title="Behavior magnitude control chart"
            subtitle="On-demand view of unsmoothed fingerprint magnitude"
            summary={`${metricSeries.length} chronological values from ${formatDecimal(Math.min(...metricSeries), 2)} to ${formatDecimal(Math.max(...metricSeries), 2)}.`}
            rows={metricSeries.map((value, index) => ({ index: index + 1, value }))}
            columns={[
              { key: "index", label: "Session order", numeric: true, value: (row) => row.index },
              {
                key: "value",
                label: "Magnitude",
                numeric: true,
                value: (row) => formatDecimal(row.value, 3),
              },
            ]}
          >
            <ControlChart data={metricSeries} width={640} height={200} />
          </ChartFrame>
        ) : null}

        <ChartFrame
          title="First drifted and recent fingerprint sessions"
          subtitle={`${driftedSessions.length} drifted · ${data.series.length} fingerprinted`}
          summary="Exact session links only; no invented Guard neighbors."
        >
          <ul className="max-h-64 space-y-1 overflow-auto font-mono text-xs">
            {(driftedSessions.length > 0
              ? driftedSessions.map((event) => ({
                  trace_id: event.trace_id!,
                  label: `${event.kind} · ${event.drifted_at ?? ""}`,
                }))
              : data.series.slice(0, 50).map((row) => ({
                  trace_id: String(row.trace_id),
                  label: String(row.ts ?? "").slice(0, 10),
                }))
            ).map((row) => (
              <li key={row.trace_id} className="flex justify-between text-cinder">
                <Link
                  to={`/sessions/${row.trace_id}`}
                  className="truncate text-bone hover:text-copper"
                >
                  {row.trace_id.slice(0, 12)}…
                </Link>
                <span>{row.label}</span>
              </li>
            ))}
          </ul>
        </ChartFrame>

        <section className="card p-4" aria-label="Behavior limitations">
          <h2 className="font-display text-base text-bone">Interpretation limits</h2>
          <ul className="mt-2 space-y-1 text-xs leading-5 text-cinder">
            {data.limitations.map((limitation) => (
              <li key={limitation}>• {limitation}</li>
            ))}
          </ul>
          {data.data_notes.length > 0 ? (
            <div className="mt-3 space-y-1 text-xs text-cinder">
              {data.data_notes.map((note, index) => (
                <p key={`${note.message}-${index}`}>{note.message}</p>
              ))}
            </div>
          ) : null}
        </section>
      </div>
    </PageShell>
  );
}

