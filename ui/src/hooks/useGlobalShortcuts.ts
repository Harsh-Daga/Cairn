import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useUiStore } from "@/state/ui";
import type { TimeRange } from "@/lib/types";
import { useTimeRangeUrlState } from "./useTimeRangeUrlState";
import { GO_SHORTCUTS } from "@/lib/navigation";

const RANGES: TimeRange[] = ["24h", "7d", "30d", "90d"];

function cycleRange(current: TimeRange, direction: 1 | -1): TimeRange {
  const index = RANGES.indexOf(current);
  const next = (index + direction + RANGES.length) % RANGES.length;
  return RANGES[next] ?? "30d";
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable;
}

export function useGlobalShortcuts(): void {
  const navigate = useNavigate();
  const { timeRange, selectPreset } = useTimeRangeUrlState();
  const paletteOpen = useUiStore((s) => s.paletteOpen);
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const shortcutsOpen = useUiStore((s) => s.shortcutsOpen);
  const setShortcutsOpen = useUiStore((s) => s.setShortcutsOpen);
  const pendingGo = useRef<string | null>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;
      const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;

      if ((event.metaKey || event.ctrlKey) && key === "k") {
        event.preventDefault();
        setPaletteOpen(!paletteOpen);
        return;
      }

      if (key === "?" && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault();
        setShortcutsOpen(!shortcutsOpen);
        return;
      }

      if (key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault();
        setPaletteOpen(true);
        return;
      }

      if (key === "Escape") {
        if (shortcutsOpen) setShortcutsOpen(false);
        if (paletteOpen) setPaletteOpen(false);
        return;
      }

      if (key === "[") {
        event.preventDefault();
        selectPreset(cycleRange(timeRange, -1));
        return;
      }

      if (key === "]") {
        event.preventDefault();
        selectPreset(cycleRange(timeRange, 1));
        return;
      }

      if (key === "g") {
        pendingGo.current = "g";
        window.setTimeout(() => {
          pendingGo.current = null;
        }, 800);
        return;
      }

      const goTarget = pendingGo.current === "g" ? GO_SHORTCUTS.get(key) : undefined;
      if (goTarget) {
        event.preventDefault();
        pendingGo.current = null;
        navigate(goTarget);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    navigate,
    paletteOpen,
    setPaletteOpen,
    setShortcutsOpen,
    selectPreset,
    shortcutsOpen,
    timeRange,
  ]);
}
