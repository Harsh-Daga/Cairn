import { useUiStore } from "@/state/ui";

const RANGES = ["24h", "7d", "30d", "90d"] as const;

export function PlaqueTopbar() {
  const timeRange = useUiStore((s) => s.timeRange);
  const setTimeRange = useUiStore((s) => s.setTimeRange);
  const watchEnabled = useUiStore((s) => s.watchEnabled);
  const setWatch = useUiStore((s) => s.setWatch);
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);

  return (
    <header className="flex h-[52px] shrink-0 items-center gap-4 border-b border-t border-quartz-vein bg-shale px-6">
      <div className="flex min-w-0 items-baseline gap-3">
        <span className="display text-[15px] text-bone">workspace</span>
        <span className="mono text-[11px] text-cinder">0 sessions · surveyed just now</span>
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

        <button
          type="button"
          className="rounded-sm border border-copper-dim px-3 py-1.5 text-xs font-medium text-copper hover:bg-granite"
        >
          Sync now
        </button>

        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          className="rounded-sm border border-quartz-vein px-3 py-1.5 font-mono text-xs text-cinder hover:text-bone"
          aria-label="Open command palette"
        >
          ⌘K
        </button>
      </div>
    </header>
  );
}
