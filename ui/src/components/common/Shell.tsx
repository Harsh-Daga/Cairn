import type { ReactNode } from "react";
import { WaypointRail } from "./WaypointRail";
import { PlaqueTopbar } from "./PlaqueTopbar";
import { CommandPalette } from "./CommandPalette";
import { KeyboardOverlay } from "./KeyboardOverlay";
import { useGlobalShortcuts } from "@/hooks/useGlobalShortcuts";
import { isStaticMode } from "@/lib/api";

interface ShellProps {
  children: ReactNode;
}

export function Shell({ children }: ShellProps) {
  useGlobalShortcuts();
  const staticMode = isStaticMode();

  return (
    <div className="flex h-full overflow-hidden">
      <WaypointRail />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <PlaqueTopbar />
        {staticMode ? (
          <div className="border-b border-ochre/40 bg-ochre/10 px-6 py-2 font-mono text-[11px] text-ochre">
            Read-only static snapshot: actions and live ingest are disabled.
          </div>
        ) : null}
        <main className="flex-1 overflow-y-auto p-6 page-enter">{children}</main>
      </div>
      <CommandPalette />
      <KeyboardOverlay />
    </div>
  );
}
