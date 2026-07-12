import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionDiffPage } from "@/pages/SessionDiff";
import { fetchTraceDiff } from "@/lib/api";
import type { TraceDiffResponse } from "@/lib/types";

vi.mock("@/lib/api", () => ({ fetchTraceDiff: vi.fn() }));

const diffPayload: TraceDiffResponse = {
  a: { trace_id: "trace-a" } as TraceDiffResponse["a"],
  b: { trace_id: "trace-b" } as TraceDiffResponse["b"],
  summary: {
    cost_a: 0.1,
    cost_b: 0.125,
    delta_cost: 0.025,
    waste_a: 100,
    waste_b: 60,
    delta_waste_tokens: -40,
    quality_a: 0.8,
    quality_b: 0.9,
    delta_quality: 0.1,
  },
  turns: [
    {
      index: 1,
      op: "match",
      a: { kind: "llm_call", name: "plan" } as TraceDiffResponse["turns"][number]["a"],
      b: { kind: "llm_call", name: "plan v2" } as TraceDiffResponse["turns"][number]["b"],
      delta_tokens: 24,
      delta_waste_tokens: -40,
      delta_quality: 0.1,
    },
  ],
};

describe("SessionDiffPage", () => {
  it("prompts to select two sessions when query params are missing", () => {
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/sessions/diff"]}>
          <SessionDiffPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Select two sessions first/i)).toBeTruthy();
  });

  it("renders deltas and aligned turns for two selected sessions", async () => {
    vi.mocked(fetchTraceDiff).mockResolvedValue(diffPayload);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/sessions/diff?a=trace-a&b=trace-b"]}>
          <SessionDiffPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText(/llm_call:plan v2/)).toBeTruthy());
    expect(fetchTraceDiff).toHaveBeenCalledWith("trace-a", "trace-b");
    expect(screen.getByText("+0.0250")).toBeTruthy();
    expect(screen.getAllByText("-40")).toHaveLength(2);
    expect(screen.getByText(/\+10\.0 pts/)).toBeTruthy();
  });
});
