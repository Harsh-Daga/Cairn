import { useEffect, useState } from "react";
import { Command, RefreshCw, Radio } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useUiStore } from "@/state/ui";
import { useToastStore } from "@/state/toast";
import { fetchWorkspace, isStaticMode, runAction } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import { connectLiveEvents } from "@/lib/sse";

const RANGES = ["24h", "7d", "30d", "90d"] as const;

export function PlaqueTopbar() {
  const queryClient = useQueryClient();
  const timeRange = useUiStore((s) => s.timeRange);
  const setTimeRange = useUiStore((s) => s.setTimeRange);
  const watchEnabled = useUiStore((s) => s.watchEnabled);
  const setWatch = useUiStore((s) => s.setWatch);
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const showToast = useToastStore((s) => s.show);
  const [ssePulse, setSsePulse] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const staticMode = isStaticMode();

  const { data: workspace } = useQuery({
    queryKey: ["workspace"],
    queryFn: fetchWorkspace,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!watchEnabled || staticMode) {
      setSsePulse(false);
      return;
    }
    return connectLiveEvents(() => {
      setSsePulse(true);
      window.setTimeout(() => setSsePulse(false), 1200);
    });
  }, [watchEnabled, staticMode]);

  const syncMut = useMutation({
    mutationFn: () => runAction("sync"),
    onMutate: () => setSyncing(true),
    onSettled: () => setSyncing(false),
    onSuccess: (res) => {
      showToast(res.ok ? "Sync started" : "Sync failed", undefined, res.ok ? "good" : "error");
      queryClient.invalidateQueries({ queryKey: ["workspace"] });
      queryClient.invalidateQueries({ queryKey: ["overview"] });
    },
    onError: () => showToast("Sync failed", undefined, "error"),
  });

  const traceCount =
    typeof workspace?.health?.trace_count === "number" ? workspace.health.trace_count : 0;
  const surveyedAt = workspace?.adapters
    .map((a) => a.cursor_updated_at)
    .filter(Boolean)
    .sort()
    .reverse()[0];
  const meta = surveyedAt
    ? `${traceCount} sessions · surveyed ${formatRelative(surveyedAt)}`
    : `${traceCount} sessions · surveyed just now`;

  return (
    <header className="flex h-[60px] shrink-0 items-center gap-4 border-b border-t border-quartz-vein/80 bg-shale/90 px-6 backdrop-blur-xl">
      <div className="flex min-w-0 items-baseline gap-3">
        <span className="display text-[15px] text-bone">{workspace?.name ?? "workspace"}</span>
        <span className="mono text-[11px] text-cinder">{meta}</span>
        {watchEnabled ? (
          <span
            className={`inline-flex items-center gap-1.5 font-mono text-[10px] ${
              ssePulse ? "text-copper" : "text-cinder"
            }`}
            title="Live SSE stream"
          >
            <Radio className="h-3 w-3" aria-hidden="true" />
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                ssePulse ? "bg-copper animate-[pulse-once_1s_ease-out]" : "bg-quartz-vein"
              }`}
              aria-hidden="true"
            />
            live
          </span>
        ) : null}
      </div>

      <div className="ml-auto flex items-center gap-2.5">
        <div
          className="flex rounded-sm border border-quartz-vein bg-slate p-0.5"
          role="group"
          aria-label="Time range"
        >
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setTimeRange(r)}
              className={`rounded-chip px-2.5 py-1 font-mono text-[11px] transition-colors ${
                timeRange === r
                  ? "bg-granite text-bone"
                  : "text-cinder hover:text-bone"
              }`}
            >
              {r}
            </button>
          ))}
        </div>

        {!staticMode ? (
          <button
            type="button"
            onClick={() => setWatch(!watchEnabled)}
            className={`rounded-sm border px-3 py-1.5 text-xs font-medium transition-colors ${
              watchEnabled
                ? "border-copper bg-copper/10 text-copper"
                : "border-quartz-vein text-cinder hover:text-bone"
            }`}
            aria-pressed={watchEnabled}
          >
            Watch
          </button>
        ) : null}

        {!staticMode ? (
          <button
            type="button"
            disabled={syncing}
            onClick={() => syncMut.mutate()}
            className="rounded-sm border border-copper-dim px-3 py-1.5 text-xs font-medium text-copper hover:bg-granite disabled:opacity-50"
          >
            <RefreshCw className={`mr-1.5 inline h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} aria-hidden="true" />
            {syncing ? "Syncing…" : "Sync now"}
          </button>
        ) : null}

        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-cinder hover:text-bone"
          aria-label="Open command palette"
        >
          <Command className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />K
        </button>
      </div>
    </header>
  );
}
