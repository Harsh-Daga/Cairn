import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ContextPage } from "@/pages/Context";
import { fetchRegions, fetchWaste } from "@/lib/api";
import type { RegionsAnalyticsResponse, WasteAnalyticsResponse } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  fetchRegions: vi.fn(),
  fetchWaste: vi.fn(),
}));

vi.mock("@/hooks/useSelectedTimeRange", () => ({
  useSelectedTimeRange: () => ({
    range: "30d" as const,
    rangeKey: "30d",
  }),
}));

const regionsPayload: RegionsAnalyticsResponse = {
  days: 30,
  resolved_range: {
    start: "2026-06-18T00:00:00+00:00",
    end: "2026-07-18T00:00:00+00:00",
    prior_start: "2026-05-19T00:00:00+00:00",
    prior_end: "2026-06-18T00:00:00+00:00",
    timezone: "UTC",
    preset: "30d",
    legacy_days: 30,
    semantics: "rolling_duration",
    duration_days: 30,
  },
  ledger: {
    conclusion:
      "Tool results dominate mapped tokens, and about 40% of mapped region tokens look like same-hash repetition.",
    mapped_region_tokens: 500,
    mapped_region_cost: 0.5,
    estimated_rebilled_tokens: 200,
    schema_overhead_tokens: 40,
    tool_result_share: 60,
    repetition_intensity: 0.4,
    primary_region: "tool_result",
    sessions_with_regions: 2,
    sessions_total: 3,
    region_coverage_pct: 66.67,
    cache_savings_available: false,
    next_action: "Inspect the top re-billed tool results block.",
    next_action_href: "/sessions/trace-1?span=span-1",
    limitation:
      "Ledger ratios use mapped region rows only; they do not prove avoidable spend or provider cache savings.",
  },
  regions: [
    { region: "tool_result", tokens: 300, spans: 4, cost: 0.3 },
    { region: "tool_schema", tokens: 40, spans: 2, cost: 0.04 },
    { region: "history", tokens: 160, spans: 3, cost: 0.16 },
  ],
  trend: [
    { day: "2026-07-01", region: "tool_result", tokens: 120, cost: 0.12 },
    { day: "2026-07-02", region: "tool_result", tokens: 180, cost: 0.18 },
  ],
  rebilled_blocks: [
    {
      block_id: "block-same",
      region: "tool_result",
      occurrences: 3,
      sessions: 2,
      tokens: 300,
      estimated_rebilled_tokens: 200,
      cost: 0.3,
      suggested_fix: "Summarize or reference large tool results after extracting needed facts.",
      evidence: {
        trace_id: "trace-1",
        span_id: "span-1",
        region: "tool_result",
        label: "Open one recorded occurrence",
      },
      limitation: "Re-billed tokens are estimated; avoidability is not inferred.",
    },
  ],
  cache_trend: [
    {
      day: "2026-07-01",
      input_tokens: 1000,
      cache_read_tokens: 100,
      cache_creation_tokens: 20,
      measured_sessions: 1,
      total_sessions: 2,
      hit_ratio: 0.09,
      estimated_savings_usd: null,
      limitation: "No savings value is estimated: provider cache pricing is not established.",
    },
  ],
  agents: [
    {
      agent_id: "main",
      sessions: 2,
      spans: 6,
      tokens: 400,
      cost: 0.4,
      top_region: "tool_result",
    },
  ],
  coverage: [
    {
      source: "cursor",
      sessions: 3,
      region_sessions: 2,
      region_coverage_pct: 66.67,
      cache_measured_sessions: 1,
      cache_coverage_pct: 33.33,
      timestamp_sessions: 3,
      dropped_events: 0,
      limitation: "Coverage reports field presence, not semantic correctness.",
    },
  ],
  schema_overhead_tokens: 40,
  schema_overhead_cost: 0.04,
  limitations: [
    "Cache savings remain unavailable without provider-specific measured billing semantics.",
    "Mapped region tokens accumulate across turns and are not a partition of input tokens.",
  ],
};

const wastePayload: WasteAnalyticsResponse = {
  days: 30,
  resolved_range: regionsPayload.resolved_range,
  categories: [{ category: "rebilling_waste", tokens: 200, events: 2 }],
  total_waste_tokens: 200,
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ContextPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ContextPage", () => {
  it("renders the answer-first ledger without inventing cache savings", async () => {
    vi.mocked(fetchRegions).mockResolvedValue(regionsPayload);
    vi.mocked(fetchWaste).mockResolvedValue(wastePayload);

    renderPage();

    expect(await screen.findByRole("heading", { name: "Where your tokens go" })).toBeTruthy();
    expect(screen.getByText(regionsPayload.ledger.conclusion)).toBeTruthy();
    expect(
      screen.getByRole("link", { name: regionsPayload.ledger.next_action }).getAttribute("href"),
    ).toBe("/sessions/trace-1?span=span-1");
    expect(screen.getByText("Unavailable")).toBeTruthy();
    expect(screen.getByText(/not a partition of input tokens/i)).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Open one recorded occurrence" }).getAttribute("href"),
    ).toBe("/sessions/trace-1?span=span-1");
    expect(screen.getByText("Estimated")).toBeTruthy();
  });
});
