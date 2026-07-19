import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  analysis: {
    tokens_a: 200,
    tokens_b: 224,
    delta_tokens: 24,
    duration_ms_a: 1_000,
    duration_ms_b: 1_500,
    delta_duration_ms: 500,
    models_a: ["model-a"],
    models_b: ["model-b"],
    regions: [
      {
        region: "tool_result",
        tokens_a: 100,
        tokens_b: 60,
        delta_tokens: -40,
        cost_a: 0.05,
        cost_b: 0.03,
        delta_cost: -0.02,
      },
    ],
    outcome_a: null,
    outcome_b: null,
    diagnostic_a: null,
    diagnostic_b: null,
    alignment_mode: "lcs",
    alignment_truncated: false,
    alignment_limitation: null,
    comparability: {
      state: "limited",
      reasons: ["Difficulty comparability is unavailable for at least one session."],
      facts: ["Both sessions use the same recorded source adapter."],
      limitation: "Descriptive only; no causal attribution.",
    },
    what_changed: [
      {
        statement: "Recorded total tokens increased by 24 tokens.",
        basis: "recorded_delta",
        evidence: [
          {
            side: "a",
            label: "Open session A",
            trace_id: "trace-a",
            span_id: null,
            evidence_type: "session",
          },
        ],
      },
    ],
    evidence: [
      {
        side: "a",
        label: "Open session A",
        trace_id: "trace-a",
        span_id: null,
        evidence_type: "session",
      },
    ],
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
        <MemoryRouter
          initialEntries={["/sessions/diff"]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
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
        <MemoryRouter
          initialEntries={["/sessions/diff?a=trace-a&b=trace-b"]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <SessionDiffPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText(/llm_call:plan v2/)).toBeTruthy());
    expect(fetchTraceDiff).toHaveBeenCalledWith("trace-a", "trace-b");
    expect(screen.getByText("+0.0250")).toBeTruthy();
    expect(screen.getAllByText("-40")).toHaveLength(3);
    expect(screen.getByText(/\+10\.0 pts/)).toBeTruthy();
    expect(screen.getByText("limited")).toBeTruthy();
    expect(screen.getByText(/Recorded total tokens increased/)).toBeTruthy();
    expect(screen.getByRole("region", { name: "Region composition difference" })).toBeTruthy();
  });

  it("progressively renders large untrusted alignments as inert text", async () => {
    const turns: TraceDiffResponse["turns"] = Array.from({ length: 201 }, (_, index) => ({
      index: index + 1,
      op: "insert",
      a: null,
      b: {
        span_id: `span-${index}`,
        kind: "llm_call",
        name: index === 0 ? "<img src=x onerror=alert(1)>" : `row-${index}`,
        input_tokens: 1,
        output_tokens: 1,
      } as TraceDiffResponse["turns"][number]["b"],
      delta_tokens: 2,
      delta_waste_tokens: 0,
      delta_quality: 1,
    }));
    vi.mocked(fetchTraceDiff).mockResolvedValue({ ...diffPayload, turns });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter
          initialEntries={["/sessions/diff?a=trace-a&b=trace-b"]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <SessionDiffPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText(/<img src=x/)).toBeTruthy());
    expect(document.querySelector("img")).toBeNull();
    expect(screen.queryByText(/row-200/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show next 1 aligned rows" }));
    expect(screen.getByText(/row-200/)).toBeTruthy();
  });
});
