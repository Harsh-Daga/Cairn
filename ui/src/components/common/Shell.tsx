import type { ReactNode } from "react";
import { WaypointRail } from "./WaypointRail";
import { PlaqueTopbar } from "./PlaqueTopbar";
import { CommandPalette } from "./CommandPalette";
import { KeyboardOverlay } from "./KeyboardOverlay";
import { useGlobalShortcuts } from "@/hooks/useGlobalShortcuts";

interface ShellProps {
  children: ReactNode;
}

export function Shell({ children }: ShellProps) {
  useGlobalShortcuts();

  return (
    <div className="flex h-full overflow-hidden">
      <WaypointRail />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <PlaqueTopbar />
        <main className="flex-1 overflow-y-auto p-6 page-enter">{children}</main>
      </div>
      <CommandPalette />
      <KeyboardOverlay />
    </div>
  );
}
