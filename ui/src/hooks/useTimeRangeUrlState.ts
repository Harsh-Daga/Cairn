import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { isStaticMode } from "@/lib/api";
import { isTimeRangePreset } from "@/lib/timeRange";
import type { CustomTimeRange, TimeRange } from "@/lib/types";
import { useUiStore } from "@/state/ui";

export function useTimeRangeUrlState() {
  const [params, setParams] = useSearchParams();
  const timeRange = useUiStore((state) => state.timeRange);
  const customTimeRange = useUiStore((state) => state.customTimeRange);
  const setTimeRange = useUiStore((state) => state.setTimeRange);
  const setCustomTimeRange = useUiStore((state) => state.setCustomTimeRange);
  const staticMode = isStaticMode();
  const serialized = params.toString();

  useEffect(() => {
    const current = new URLSearchParams(serialized);
    const preset = current.get("range");
    const start = current.get("start");
    const end = current.get("end");
    const timezone = current.get("tz") || "UTC";
    if (!staticMode && start && end) {
      if (
        customTimeRange?.start !== start ||
        customTimeRange.end !== end ||
        customTimeRange.timezone !== timezone
      ) {
        setCustomTimeRange({ start, end, timezone });
      }
    } else if (isTimeRangePreset(preset) && (timeRange !== preset || customTimeRange !== null)) {
      setTimeRange(preset);
    }
  }, [customTimeRange, serialized, setCustomTimeRange, setTimeRange, staticMode, timeRange]);

  const replaceRangeParams = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params);
    next.delete("range");
    next.delete("start");
    next.delete("end");
    next.delete("tz");
    next.delete("days");
    mutate(next);
    next.delete("page");
    setParams(next);
  };

  const selectPreset = (preset: TimeRange) => {
    setTimeRange(preset);
    replaceRangeParams((next) => next.set("range", preset));
  };

  const selectCustom = (range: CustomTimeRange) => {
    if (staticMode) return;
    setCustomTimeRange(range);
    replaceRangeParams((next) => {
      next.set("start", range.start);
      next.set("end", range.end);
      next.set("tz", range.timezone);
    });
  };

  return { timeRange, customTimeRange, selectPreset, selectCustom, staticMode };
}
