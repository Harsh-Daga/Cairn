import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { WaypointRail } from "./WaypointRail";
import { PlaqueTopbar } from "./PlaqueTopbar";
import { CommandPalette } from "./CommandPalette";
import { KeyboardOverlay } from "./KeyboardOverlay";
import { useGlobalShortcuts } from "@/hooks/useGlobalShortcuts";
import { fetchStaticManifest, isStaticMode } from "@/lib/api";
import { MobileDock } from "./MobileDock";
import { AdapterHealthBanner } from "./AdapterHealthBanner";

interface ShellProps {
  children: ReactNode;
}

export function Shell({ children }: ShellProps) {
  useGlobalShortcuts();
  const staticMode = isStaticMode();
  const { data: staticManifest } = useQuery({
    queryKey: ["static-manifest"],
    queryFn: fetchStaticManifest,
    enabled: staticMode,
    staleTime: Infinity,
  });

  return (
    <div className="flex h-full overflow-hidden">
      <a
        href="#main-content"
        className="fixed left-3 top-3 z-[100] -translate-y-20 rounded-sm bg-copper px-4 py-2 font-medium text-anthracite shadow-stone transition-transform focus:translate-y-0"
      >
        Skip to main content
      </a>
      <WaypointRail />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <PlaqueTopbar />
        <AdapterHealthBanner />
        {staticMode ? (
          <div className="border-b border-ochre/40 bg-ochre/10 px-6 py-2 font-mono text-[11px] text-ochre">
            Read-only scrubbed snapshot
            {staticManifest?.captured_at
              ? ` captured ${new Date(staticManifest.captured_at).toLocaleString()}`
              : ""}
            : actions, live ingest, custom ranges, arbitrary filters, pagination, and uncaptured
            views are unavailable.
          </div>
        ) : null}
        <main
          id="main-content"
          tabIndex={0}
          className="workspace-main flex-1 overflow-y-auto p-6 page-enter"
        >
          {children}
        </main>
      </div>
      <MobileDock />
      <CommandPalette />
      <KeyboardOverlay />
    </div>
  );
}
