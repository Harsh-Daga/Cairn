import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InsightCard } from "@/components/insights/InsightCard";
import type { InsightRow } from "@/lib/types";
import { splitInsights } from "@/pages/Insights";

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
};

describe("insight action contract", () => {
  it("shows the null-savings reason and copies the structured fix", () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <InsightCard insight={base} expanded onToggle={() => undefined} onAck={() => undefined} />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Savings not priced: Per-retry cost/)).toBeTruthy();
    expect(screen.getByText("Read the error before retrying.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copy fix" }));
    expect(writeText).toHaveBeenCalledWith("Read the error before retrying.");
  });

  it("separates non-actionable evidence into diagnostics", () => {
    const split = splitInsights([base, { ...base, insight_id: "i2", diagnostic: true }]);
    expect(split.recommendations.map((row) => row.insight_id)).toEqual(["i1"]);
    expect(split.diagnostics.map((row) => row.insight_id)).toEqual(["i2"]);
  });
});
