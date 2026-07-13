import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { fetchExperimentDetail, fetchExperiments, runAction } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { useToastStore } from "@/state/toast";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";
import { IntervalPlot } from "@/components/charts";
import { VerdictPreview } from "@/components/optimize/VerdictPreview";
import type { VerdictPreviewData } from "@/lib/types";

const STATIONS = ["proposed", "applied", "measuring", "verdict"] as const;

function ExperimentCard({
  experimentId,
  status,
  targetFile,
  verdict,
  liftPct,
  createdAt,
  preview,
  onApply,
  onRevert,
  onMeasure,
}: {
  experimentId: string;
  status: string;
  targetFile: string | null;
  verdict: string | null;
  liftPct: number | null;
  createdAt: string;
  preview?: VerdictPreviewData | null;
  onApply: () => void;
  onRevert: () => void;
  onMeasure: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const detailQ = useQuery({
    queryKey: ["experiment", experimentId],
    queryFn: () => fetchExperimentDetail(experimentId),
    enabled: expanded,
  });

  const exp = detailQ.data?.experiment;
  const detailPreview = detailQ.data?.preview as VerdictPreviewData | null | undefined;
  const cardPreview = preview ?? detailPreview;
  const content = typeof exp?.content === "string" ? exp.content : null;
  const liftCiLow = exp?.effect_ci_low != null ? Number(exp.effect_ci_low) : null;
  const liftCiHigh = exp?.effect_ci_high != null ? Number(exp.effect_ci_high) : null;
  const liftEstimate = liftPct ?? (exp?.effect_estimate != null ? Number(exp.effect_estimate) : null);

  return (
    <div className="card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Chip label={status} tone={status === "verdict" ? "malachite" : "default"} />
        {targetFile ? <Chip label={targetFile} /> : null}
        {verdict ? <Chip label={verdict} tone="copper" /> : null}
      </div>
      <p className="mt-2 font-mono text-xs text-cinder">
        {experimentId.slice(0, 12)}… · {formatRelative(createdAt)}
      </p>
      {status === "proposed" && cardPreview ? <VerdictPreview preview={cardPreview} /> : null}
      {liftEstimate != null ? (
        <p className="mt-1 font-mono text-sm text-bone">
          Effect: {(liftEstimate * 100).toFixed(1)}%
        </p>
      ) : null}
      {liftCiLow != null && liftCiHigh != null && liftEstimate != null ? (
        <div className="mt-3">
          <IntervalPlot
            points={[
              {
                label: "lift",
                value: liftEstimate,
                low: liftCiLow,
                high: liftCiHigh,
              },
            ]}
            width={320}
            height={80}
          />
        </div>
      ) : null}
      <button
        type="button"
        className="mt-2 font-mono text-[10px] text-copper hover:underline"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? "Hide diff" : "Preview diff"}
      </button>
      {expanded && content ? (
        <pre className="mt-2 max-h-48 overflow-auto rounded-sm bg-granite/40 p-3 font-mono text-[10px] text-bone">
          {content.slice(0, 2000)}
        </pre>
      ) : null}
      {expanded && !content && detailQ.isLoading ? (
        <p className="mt-2 text-xs text-cinder">Loading content…</p>
      ) : null}
      <div className="mt-3 flex gap-2">
        {status === "proposed" ? (
          <button
            type="button"
            className="rounded-sm bg-copper px-3 py-1.5 font-mono text-xs text-anthracite"
            onClick={onApply}
          >
            Apply
          </button>
        ) : null}
        {status === "applied" || status === "measuring" ? (
          <>
            <button
              type="button"
              className="rounded-sm bg-copper px-3 py-1.5 font-mono text-xs text-anthracite"
              onClick={onMeasure}
            >
              Measure now
            </button>
            <button
              type="button"
              className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-bone"
              onClick={onRevert}
            >
              Revert
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
}

export function OptimizePage() {
  const queryClient = useQueryClient();
  const showToast = useToastStore((s) => s.show);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["experiments"],
    queryFn: fetchExperiments,
  });

  const applyMut = useMutation({
    mutationFn: (id: string) => runAction("experiment_apply", { experiment_id: id }),
    onSuccess: () => {
      showToast("Experiment applied");
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
    onError: () => showToast("Apply failed", undefined, "error"),
  });

  const revertMut = useMutation({
    mutationFn: (id: string) => runAction("experiment_revert", { experiment_id: id }),
    onSuccess: () => {
      showToast("Experiment reverted", () => undefined);
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
    onError: () => showToast("Revert failed", undefined, "error"),
  });

  const measureMut = useMutation({
    mutationFn: (id: string) => runAction("experiment_measure", { experiment_id: id }),
    onSuccess: () => {
      showToast("Experiment measured");
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
    onError: () => showToast("Measurement failed", undefined, "error"),
  });

  const proposeMut = useMutation({
    mutationFn: () => runAction("optimize_propose"),
    onSuccess: () => {
      showToast("Proposals generated");
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
    onError: () => showToast("Proposal generation failed", undefined, "error"),
  });

  if (isLoading) {
    return (
      <PageShell title="Optimize" question="Turn evidence into controlled instruction changes, then prove whether they worked.">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell title="Optimize" question="Turn evidence into controlled instruction changes, then prove whether they worked.">
        <ErrorCard />
      </PageShell>
    );
  }

  const byStatus = STATIONS.reduce(
    (acc, s) => {
      acc[s] = data.experiments.filter((e) => e.status === s);
      return acc;
    },
    {} as Record<(typeof STATIONS)[number], typeof data.experiments>,
  );

  if (data.experiments.length === 0) {
    return (
      <PageShell title="Optimize" question="Turn evidence into controlled instruction changes, then prove whether they worked.">
        <EmptyCard
          title="No proposals yet"
          detail="Cairn needs about a week of sessions to find leverage. Run sync and check Insights first."
          action={
            <button
              type="button"
              className="rounded-sm bg-copper px-3 py-2 font-mono text-xs text-anthracite"
              onClick={() => proposeMut.mutate()}
            >
              Generate proposals
            </button>
          }
        />
      </PageShell>
    );
  }

  return (
    <PageShell title="Optimize" question="Turn evidence into controlled instruction changes, then prove whether they worked.">
      <div className="space-y-6">
        <div className="card p-4">
          <div className="flex flex-wrap items-center gap-2">
            {STATIONS.map((station, i) => (
              <div key={station} className="flex items-center gap-2">
                <div
                  className={`min-w-[100px] rounded-sm border px-3 py-2 text-center ${
                    byStatus[station].length > 0
                      ? "border-copper/50 bg-copper/10"
                      : "border-quartz-vein bg-granite/20"
                  }`}
                >
                  <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">
                    {station}
                  </p>
                  <p className="mt-0.5 font-display text-xl text-bone">
                    {byStatus[station].length}
                  </p>
                </div>
                {i < STATIONS.length - 1 ? (
                  <span className="font-mono text-cinder" aria-hidden="true">
                    →
                  </span>
                ) : null}
              </div>
            ))}
          </div>
          <p className="mt-3 border-t border-quartz-vein/50 pt-3 font-mono text-[10px] text-cinder">
            Reflector: proposals flow left-to-right — apply to measure, measure to verdict.
          </p>
        </div>

        <div className="space-y-3">
          {data.experiments.map((exp) => (
            <ExperimentCard
              key={exp.experiment_id}
              experimentId={exp.experiment_id}
              status={exp.status}
              targetFile={exp.target_file}
              verdict={exp.verdict}
              liftPct={exp.lift_pct}
              createdAt={exp.created_at}
              onApply={() => applyMut.mutate(exp.experiment_id)}
              onRevert={() => revertMut.mutate(exp.experiment_id)}
              onMeasure={() => measureMut.mutate(exp.experiment_id)}
            />
          ))}
        </div>

        <button
          type="button"
          className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone hover:bg-granite"
          onClick={() => proposeMut.mutate()}
        >
          Generate proposals
        </button>
      </div>
    </PageShell>
  );
}
