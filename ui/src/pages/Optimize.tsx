import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchExperiments, runAction } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { useToastStore } from "@/state/toast";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import { EmptyCard, ErrorCard } from "@/components/common/DataViews";

const STATIONS = ["proposed", "applied", "measuring", "verdict"] as const;

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
  });

  const revertMut = useMutation({
    mutationFn: (id: string) => runAction("experiment_revert", { experiment_id: id }),
    onSuccess: () => {
      showToast("Experiment reverted", () => undefined);
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
    },
  });

  if (isLoading) {
    return (
      <PageShell title="Optimize" question="Close the loop: propose → apply → measure → verdict.">
        <div className="card h-32 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell title="Optimize" question="Close the loop: propose → apply → measure → verdict.">
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
      <PageShell title="Optimize" question="Close the loop: propose → apply → measure → verdict.">
        <EmptyCard
          title="No proposals yet"
          detail="Cairn needs about a week of sessions to find leverage. Run sync and check Insights first."
          action={
            <button
              type="button"
              className="rounded-sm bg-copper px-3 py-2 font-mono text-xs text-anthracite"
              onClick={() => runAction("optimize_propose")}
            >
              Generate proposals
            </button>
          }
        />
      </PageShell>
    );
  }

  return (
    <PageShell title="Optimize" question="Close the loop: propose → apply → measure → verdict.">
      <div className="space-y-6">
        <div className="flex flex-wrap gap-3">
          {STATIONS.map((station) => (
            <div key={station} className="card min-w-[120px] flex-1 p-3 text-center">
              <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">
                {station}
              </p>
              <p className="mt-1 font-display text-xl text-bone">
                {byStatus[station].length}
              </p>
            </div>
          ))}
        </div>

        <div className="space-y-3">
          {data.experiments.map((exp) => (
            <div key={exp.experiment_id} className="card p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Chip label={exp.status} tone={exp.status === "verdict" ? "malachite" : "default"} />
                {exp.target_file ? <Chip label={exp.target_file} /> : null}
                {exp.verdict ? <Chip label={exp.verdict} tone="copper" /> : null}
              </div>
              <p className="mt-2 font-mono text-xs text-cinder">
                {exp.experiment_id.slice(0, 12)}… · {formatRelative(exp.created_at)}
              </p>
              {exp.lift_pct != null ? (
                <p className="mt-1 font-mono text-sm text-bone">
                  Effect: {(exp.lift_pct * 100).toFixed(1)}%
                </p>
              ) : null}
              <div className="mt-3 flex gap-2">
                {exp.status === "proposed" ? (
                  <button
                    type="button"
                    className="rounded-sm bg-copper px-3 py-1.5 font-mono text-xs text-anthracite"
                    onClick={() => applyMut.mutate(exp.experiment_id)}
                  >
                    Apply
                  </button>
                ) : null}
                {exp.status === "applied" || exp.status === "measuring" ? (
                  <button
                    type="button"
                    className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-bone"
                    onClick={() => revertMut.mutate(exp.experiment_id)}
                  >
                    Revert
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>

        <button
          type="button"
          className="rounded-sm border border-quartz-vein px-3 py-2 font-mono text-xs text-bone hover:bg-granite"
          onClick={() => runAction("optimize_propose")}
        >
          Generate proposals
        </button>
      </div>
    </PageShell>
  );
}
