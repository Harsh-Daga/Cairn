import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InsightCard } from "@/components/insights/InsightCard";
import type { InsightRow } from "@/lib/types";
import { splitInsights } from "@/lib/insights";

const base: InsightRow = {
  insight_id: "i1",
  fingerprint: "retry",
  detector: "retry",
  severity: "warning",
  title: "Retry loop",
  body: "The same failure repeated.",
  state: "new",
  savings_estimate: null,
  savings_unavailable_reason: "Per-retry cost is unavailable.",
  fix: { kind: "instruction", label: "Copy rule", value: "Read the error before retrying." },
  diagnostic: false,
  action: null,
  last_seen_at: "2026-01-01T00:00:00Z",
  rank_score: 0.42,
  impact: null,
  confidence: "low",
  recurrence: 1,
  snoozed_until: null,
  suppressed_duplicate: false,
};

describe("insight action contract", () => {
  it("shows rank metadata and snooze/ack actions", () => {
    const onAck = vi.fn();
    const onSnooze = vi.fn();
    render(
      <InsightCard
        insight={base}
        selected
        onSelect={() => undefined}
        onAck={onAck}
        onSnooze={onSnooze}
      />,
    );
    expect(screen.getByText(/unpriced/)).toBeTruthy();
    expect(screen.getByText(/rank/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Ack" }));
    fireEvent.click(screen.getByRole("button", { name: "Snooze 14d" }));
    expect(onAck).toHaveBeenCalledWith(base);
    expect(onSnooze).toHaveBeenCalledWith(base);
  });

  it("separates non-actionable evidence into diagnostics", () => {
    const split = splitInsights([base, { ...base, insight_id: "i2", diagnostic: true }]);
    expect(split.recommendations.map((row) => row.insight_id)).toEqual(["i1"]);
    expect(split.diagnostics.map((row) => row.insight_id)).toEqual(["i2"]);
  });
});
