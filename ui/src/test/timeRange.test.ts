import { describe, expect, it } from "vitest";
import {
  isTimeRangePreset,
  selectedTimeRange,
  timeRangeKey,
  timeRangeLabel,
  timeRangeParams,
} from "@/lib/timeRange";

describe("cross-layer time range", () => {
  it("uses explicit preset parameters live and legacy captured days in static mode", () => {
    const live = timeRangeParams("7d");
    expect(live.get("preset")).toBe("7d");
    expect(live.get("timezone")).toBeTruthy();
    expect(live.has("days")).toBe(false);

    expect(timeRangeParams("7d", true).toString()).toBe("days=7");
  });

  it("serializes custom half-open bounds and has a stable query key", () => {
    const custom = {
      start: "2026-07-01T09:00",
      end: "2026-07-02T09:00",
      timezone: "Asia/Kolkata",
    };
    expect(timeRangeParams(custom).toString()).toBe(
      "start=2026-07-01T09%3A00&end=2026-07-02T09%3A00&timezone=Asia%2FKolkata",
    );
    expect(timeRangeKey(custom)).toBe("custom:2026-07-01T09:00:2026-07-02T09:00:Asia/Kolkata");
    expect(timeRangeLabel(custom)).toBe("selected custom range");
    expect(() => timeRangeParams(custom, true)).toThrow("unavailable");
  });

  it("selects custom state over the persisted preset and validates URL presets", () => {
    const custom = { start: "a", end: "b", timezone: "UTC" };
    expect(selectedTimeRange("30d", custom)).toEqual(custom);
    expect(isTimeRangePreset("90d")).toBe(true);
    expect(isTimeRangePreset("365d")).toBe(false);
  });
});
