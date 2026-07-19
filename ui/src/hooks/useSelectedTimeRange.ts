import { selectedTimeRange, timeRangeKey } from "@/lib/timeRange";
import { useUiStore } from "@/state/ui";

export function useSelectedTimeRange() {
  const preset = useUiStore((state) => state.timeRange);
  const custom = useUiStore((state) => state.customTimeRange);
  const range = selectedTimeRange(preset, custom);
  return { range, rangeKey: timeRangeKey(range) };
}
