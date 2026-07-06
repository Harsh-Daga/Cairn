import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useUiStore } from "@/state/ui";
import type { TimeRange } from "@/lib/types";

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
  const timeRange = useUiStore((s) => s.timeRange);
  const setTimeRange = useUiStore((s) => s.setTimeRange);
  const paletteOpen = useUiStore((s) => s.paletteOpen);
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen);
  const shortcutsOpen = useUiStore((s) => s.shortcutsOpen);
  const setShortcutsOpen = useUiStore((s) => s.setShortcutsOpen);
  const pendingGo = useRef<string | null>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(!paletteOpen);
        return;
      }

      if (event.key === "?" && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault();
        setShortcutsOpen(!shortcutsOpen);
        return;
      }

      if (event.key === "Escape") {
        if (shortcutsOpen) setShortcutsOpen(false);
        if (paletteOpen) setPaletteOpen(false);
        return;
      }

      if (event.key === "[") {
        event.preventDefault();
        setTimeRange(cycleRange(timeRange, -1));
        return;
      }

      if (event.key === "]") {
        event.preventDefault();
        setTimeRange(cycleRange(timeRange, 1));
        return;
      }

      if (event.key === "g") {
        pendingGo.current = "g";
        window.setTimeout(() => {
          pendingGo.current = null;
        }, 800);
        return;
      }

      if (event.key === "s" && pendingGo.current === "g") {
        event.preventDefault();
        pendingGo.current = null;
        navigate("/sessions");
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    navigate,
    paletteOpen,
    setPaletteOpen,
    setShortcutsOpen,
    setTimeRange,
    shortcutsOpen,
    timeRange,
  ]);
}
