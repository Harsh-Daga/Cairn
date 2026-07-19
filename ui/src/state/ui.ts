import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CustomTimeRange, TimeRange } from "@/lib/types";
import { applyThemePreference, normalizeThemePreference, type ThemePreference } from "@/lib/theme";

interface UiState {
  railCollapsed: boolean;
  timeRange: TimeRange;
  customTimeRange: CustomTimeRange | null;
  watchEnabled: boolean;
  paletteOpen: boolean;
  shortcutsOpen: boolean;
  themePreference: ThemePreference;
  toggleRail: () => void;
  setTimeRange: (range: TimeRange) => void;
  setCustomTimeRange: (range: CustomTimeRange) => void;
  setWatch: (on: boolean) => void;
  setPaletteOpen: (open: boolean) => void;
  setShortcutsOpen: (open: boolean) => void;
  setThemePreference: (preference: ThemePreference) => void;
}

export function migrateUiState(persisted: unknown): UiState {
  const state =
    persisted && typeof persisted === "object" ? (persisted as Record<string, unknown>) : {};
  return {
    ...state,
    themePreference: normalizeThemePreference(
      state.themePreference ?? state.theme ?? state.colorScheme,
    ),
  } as unknown as UiState;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      railCollapsed: false,
      timeRange: "30d",
      customTimeRange: null,
      watchEnabled: true,
      paletteOpen: false,
      shortcutsOpen: false,
      themePreference: "system",
      toggleRail: () => set((s) => ({ railCollapsed: !s.railCollapsed })),
      setTimeRange: (timeRange) => set({ timeRange, customTimeRange: null }),
      setCustomTimeRange: (customTimeRange) => set({ customTimeRange }),
      setWatch: (watchEnabled) => set({ watchEnabled }),
      setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
      setShortcutsOpen: (shortcutsOpen) => set({ shortcutsOpen }),
      setThemePreference: (themePreference) => {
        applyThemePreference(themePreference);
        set({ themePreference });
      },
    }),
    {
      name: "cairn-ui",
      version: 1,
      migrate: migrateUiState,
    },
  ),
);
