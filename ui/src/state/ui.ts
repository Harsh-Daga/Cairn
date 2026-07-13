import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { TimeRange } from "@/lib/types";

interface UiState {
  railCollapsed: boolean;
  timeRange: TimeRange;
  watchEnabled: boolean;
  paletteOpen: boolean;
  shortcutsOpen: boolean;
  toggleRail: () => void;
  setTimeRange: (range: TimeRange) => void;
  setWatch: (on: boolean) => void;
  setPaletteOpen: (open: boolean) => void;
  setShortcutsOpen: (open: boolean) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      railCollapsed: false,
      timeRange: "30d",
      watchEnabled: true,
      paletteOpen: false,
      shortcutsOpen: false,
      toggleRail: () => set((s) => ({ railCollapsed: !s.railCollapsed })),
      setTimeRange: (timeRange) => set({ timeRange }),
      setWatch: (watchEnabled) => set({ watchEnabled }),
      setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
      setShortcutsOpen: (shortcutsOpen) => set({ shortcutsOpen }),
    }),
    { name: "cairn-ui" },
  ),
);
