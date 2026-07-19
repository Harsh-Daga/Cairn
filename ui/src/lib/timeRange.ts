import type { CustomTimeRange, TimeRange, TimeRangeRequest } from "./types";

const PRESETS = new Set<TimeRange>(["24h", "7d", "30d", "90d"]);

export function isTimeRangePreset(value: string | null): value is TimeRange {
  return value !== null && PRESETS.has(value as TimeRange);
}

export function selectedTimeRange(
  preset: TimeRange,
  custom: CustomTimeRange | null,
): TimeRangeRequest {
  return custom ?? preset;
}

export function timeRangeKey(range: TimeRangeRequest): string {
  return typeof range === "string"
    ? `preset:${range}`
    : `custom:${range.start}:${range.end}:${range.timezone}`;
}

export function timeRangeLabel(range: TimeRangeRequest): string {
  if (typeof range !== "string") return "selected custom range";
  return range === "24h" ? "last 24 hours" : `last ${timeRangeDays(range)} days`;
}

export function timeRangeParams(
  range: TimeRangeRequest | number,
  staticMode = false,
): URLSearchParams {
  const params = new URLSearchParams();
  if (typeof range === "number") {
    params.set("days", String(range));
    return params;
  }
  if (typeof range === "string") {
    if (staticMode) {
      params.set("days", String(timeRangeDays(range)));
    } else {
      params.set("preset", range);
      params.set("timezone", Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
    }
    return params;
  }
  if (staticMode) {
    throw new Error(
      "Custom time ranges are unavailable in this static snapshot. Choose a captured preset.",
    );
  }
  params.set("start", range.start);
  params.set("end", range.end);
  params.set("timezone", range.timezone);
  return params;
}

export function timeRangeDays(range: TimeRangeRequest): number {
  if (typeof range !== "string") {
    const milliseconds = new Date(range.end).getTime() - new Date(range.start).getTime();
    return Math.max(1, Math.ceil(milliseconds / 86_400_000));
  }
  switch (range) {
    case "24h":
      return 1;
    case "7d":
      return 7;
    case "30d":
      return 30;
    case "90d":
      return 90;
  }
}
