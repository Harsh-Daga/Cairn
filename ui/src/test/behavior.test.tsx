import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { fetchBehavior } from "@/lib/api";
import type { BehaviorResponse } from "@/lib/generated/api-types";
import { BehaviorPage } from "@/pages/Behavior";

vi.mock("@/lib/api", () => ({
  fetchBehavior: vi.fn(),
  timeRangeDays: vi.fn(() => 30),
}));

describe("BehaviorPage", () => {
  it("shows experimental baseline progress without hiding low-n trends", async () => {
    const payload: BehaviorResponse = {
      days: 30,
      resolved_range: {
        start: "2026-06-17T00:00:00Z",
        end: "2026-07-17T00:00:00Z",
        prior_start: "2026-05-18T00:00:00Z",
        prior_end: "2026-06-17T00:00:00Z",
        timezone: "UTC",
        preset: "30d",
        legacy_days: null,
        semantics: "rolling_duration",
        duration_days: 30,
      },
      ledger: {
        conclusion: "Joint-shock baseline still collecting (12/20); EWMA trend remains active.",
        fingerprint_sessions: 3,
        drift_events: 0,
        baseline_ready: false,
        baseline_collected: 12,
        baseline_required: 20,
        primary_axis: null,
        next_action: "Accumulate matched project/model sessions",
        next_action_href: "/sessions",
        limitation: "Behavior drift is descriptive association with a local fingerprint baseline.",
      },
      series: [
        { trace_id: "t1", ts: "2026-07-01", vector: [1, 2, 3], project: "p", model: "m" },
        { trace_id: "t2", ts: "2026-07-02", vector: [2, 3, 4], project: "p", model: "m" },
        { trace_id: "t3", ts: "2026-07-03", vector: [3, 4, 5], project: "p", model: "m" },
      ],
      drift: [],
      radar: null,
      baseline_progress: {
        collected: 12,
        required: 20,
        ready: false,
        note: "12/20 sessions collected",
      },
      data_notes: [],
      limitations: [
        "Joint-shock drift requires a project/model baseline of 20 sessions.",
        "Nearby Guard instruction-file events are listed on /guard when present for the range.",
      ],
    };
    vi.mocked(fetchBehavior).mockResolvedValue(payload);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <BehaviorPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText("12/20 sessions collected")).toBeTruthy());
    expect(screen.getByText("Experimental")).toBeTruthy();
    expect(screen.getByText("Fingerprint vs baseline")).toBeTruthy();
    expect(screen.getByText("Behavior trend (EWMA)")).toBeTruthy();
    expect(screen.queryByText(/No drift/)).toBeNull();
    expect(screen.getAllByText(/Guard/i).length).toBeGreaterThan(0);
  });
});
