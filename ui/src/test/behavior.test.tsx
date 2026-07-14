import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { fetchBehavior } from "@/lib/api";
import type { BehaviorResponse } from "@/lib/types";
import { BehaviorPage } from "@/pages/Behavior";

vi.mock("@/lib/api", () => ({
  fetchBehavior: vi.fn(),
  timeRangeDays: vi.fn(() => 30),
}));

describe("BehaviorPage", () => {
  it("shows experimental baseline progress without hiding low-n trends", async () => {
    const payload: BehaviorResponse = {
      days: 30,
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
    };
    vi.mocked(fetchBehavior).mockResolvedValue(payload);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <BehaviorPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText("12/20 sessions collected")).toBeTruthy());
    expect(screen.getByText("Experimental")).toBeTruthy();
    expect(screen.getByText("Behavior trend")).toBeTruthy();
    expect(screen.queryByText(/No drift/)).toBeNull();
  });
});
