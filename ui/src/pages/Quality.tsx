import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchQuality, runAction, timeRangeDays } from "@/lib/api";
import { formatCost } from "@/lib/format";
import { useUiStore } from "@/state/ui";
import { useToastStore } from "@/state/toast";
import { PageShell } from "@/components/common/PageShell";
import { ChartFrame } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { HorizontalBars, Sparkline } from "@/components/charts";
import { QualityScoreDetails } from "@/components/quality/QualityScoreDetails";

export function QualityPage() {
  const timeRange = useUiStore((s) => s.timeRange);
  const days = timeRangeDays(timeRange);
  const showToast = useToastStore((s) => s.show);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["quality", days],
    queryFn: () => fetchQuality(days),
  });

  const checkMut = useMutation({
    mutationFn: () => runAction("check"),
    onSuccess: (res) => {
      const ok = res.ok && res.result?.passed !== false;
      showToast(ok ? "CI gate passed" : "CI gate failed");
    },
    onError: () => showToast("CI gate check failed"),
  });

  if (isLoading) {
    return (
      <PageShell title="Quality" question="Connect agent activity to outcomes, reliability, and the true cost of success.">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell title="Quality" question="Connect agent activity to outcomes, reliability, and the true cost of success.">
        <ErrorCard />
      </PageShell>
    );
  }

  if (data.outcomes.length === 0) {
    return (
      <PageShell title="Quality" question="Connect agent activity to outcomes, reliability, and the true cost of success.">
        <EmptyCard
          title="Outcomes not captured yet"
          detail="Enable outcome capture in Settings to score sessions against git and tests."
          action={
            <button
              type="button"
              className="rounded-sm bg-copper px-3 py-2 font-mono text-xs text-anthracite"
              onClick={() => runAction("config_set", { key: "outcomes.enabled", value: true })}
            >
              Enable outcome capture
            </button>
          }
        />
      </PageShell>
    );
  }

  const passed = data.outcomes.filter(
    (o) => Number(o.tests_run ?? 0) > 0 && Number(o.tests_failed ?? 0) === 0,
  ).length;
  const landed = data.outcomes.filter((o) => Number(o.commit_landed ?? 0) > 0).length;
  const funnel = [
    { label: "Sessions scored", value: data.outcomes.length },
    { label: "Tests passed", value: passed },
    { label: "Commits landed", value: landed },
  ];

  const cpsSeries = data.cost_per_success
    .map((row) => Number(row.cost_per_success))
    .filter((v) => Number.isFinite(v));

  return (
    <PageShell title="Quality" question="Connect agent activity to outcomes, reliability, and the true cost of success.">
      <div className="space-y-6">
        <div className="card p-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h3 className="font-display text-sm text-bone">CI quality gate</h3>
              <p className="mt-1 text-sm text-cinder">
                Run the local check action against current workspace outcomes.
              </p>
            </div>
            <button
              type="button"
              className="rounded-sm bg-copper px-3 py-2 font-mono text-xs text-anthracite disabled:opacity-50"
              disabled={checkMut.isPending}
              onClick={() => checkMut.mutate()}
            >
              {checkMut.isPending ? "Running…" : "Run check"}
            </button>
          </div>
        </div>

        <ChartFrame title="Outcome funnel" subtitle="From session to landed commit">
          <HorizontalBars
            items={funnel}
            width={480}
          />
        </ChartFrame>

        {data.histogram.length > 0 ? (
          <ChartFrame title="Quality histogram" subtitle="Score distribution 0–100">
            <HorizontalBars
              items={data.histogram.map((bucket) => ({
                label: bucket.bucket,
                value: bucket.count,
              }))}
              width={480}
            />
          </ChartFrame>
        ) : null}

        {cpsSeries.length > 1 ? (
          <ChartFrame title="Cost per success" subtitle="Trend over scored sessions">
            <Sparkline data={cpsSeries} width={480} height={64} />
          </ChartFrame>
        ) : null}

        <div className="card overflow-hidden">
          <div className="border-b border-quartz-vein px-4 py-3">
            <h3 className="font-display text-sm text-bone">Recent outcomes</h3>
          </div>
          <table className="w-full text-left text-sm">
            <thead className="font-mono text-[10px] uppercase tracking-wide text-cinder">
              <tr>
                <th className="px-4 py-2">Session</th>
                <th className="px-4 py-2">Score</th>
                <th className="px-4 py-2">Tests</th>
                <th className="px-4 py-2">Cost/success</th>
              </tr>
            </thead>
            <tbody>
              {data.outcomes.slice(0, 20).map((o) => (
                <tr key={String(o.trace_id)} className="border-t border-quartz-vein/50">
                  <td className="px-4 py-2">
                    <Link
                      to={`/sessions/${String(o.trace_id)}`}
                      className="font-mono text-xs text-copper hover:underline"
                    >
                      {String(o.trace_id).slice(0, 10)}…
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-xs text-bone">
                    {o.quality_score != null ? (
                      <QualityScoreDetails
                        score={Number(o.quality_score)}
                        components={o.quality_components}
                        weights={o.quality_weights}
                      />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-cinder">
                    {String(o.tests_passed ?? 0)}/{String(o.tests_run ?? 0)}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-bone">
                    {o.cost_per_success != null
                      ? formatCost(Number(o.cost_per_success))
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </PageShell>
  );
}
