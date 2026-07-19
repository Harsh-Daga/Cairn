import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { fetchGuard } from "@/lib/api";
import type { GuardAnalyticsResponse } from "@/lib/types";
import { GuardPage } from "@/pages/Guard";

vi.mock("@/lib/api", () => ({
  fetchGuard: vi.fn(),
}));

vi.mock("@/hooks/useSelectedTimeRange", () => ({
  useSelectedTimeRange: () => ({ range: 30, rangeKey: "30" }),
}));

describe("GuardPage", () => {
  it("shows ledger and non-causal association language", async () => {
    const payload: GuardAnalyticsResponse = {
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
        conclusion:
          "1 instruction-file event(s) in range; 1 with pre/post association; 0 confounded.",
        event_count: 1,
        associated_count: 1,
        confounded_count: 0,
        git_state: "clean",
        next_action: "Review AGENTS.md event",
        next_action_href: "/guard?event=grd_demo",
        limitation:
          "Before/after session metrics are associations observed around instruction edits, not causal proof.",
      },
      events: [
        {
          event_id: "grd_demo",
          occurred_at: "2026-07-01T00:00:00Z",
          path_rel: "AGENTS.md",
          event_kind: "edit",
          commit_sha: "abcd1234abcd",
          parent_sha: "bbbb2222bbbb",
          before_hash: "h1",
          after_hash: "h2",
          diff_summary: "AGENTS.md | 1 file changed",
          git_state: "clean",
          source: "git",
          confound_notes: [],
          linked_experiment_id: "exp-1",
          association: {
            metric: "cost_per_session",
            effect_estimate: -0.2,
            effect_ci_low: -0.4,
            effect_ci_high: -0.05,
            pre_n: 8,
            post_n: 9,
            verdict: "improved",
            language: "associated_with",
            confound_notes: [],
            limitation: "Association language stays non-causal.",
          },
          optimize_href: "/optimize?experiment=exp-1&tab=portfolio",
          event_href: "/guard?event=grd_demo",
        },
      ],
      limitations: ["Raw instruction text is scrubbed."],
    };
    vi.mocked(fetchGuard).mockResolvedValue(payload);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <GuardPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText("Instruction edits under association, not causation")).toBeTruthy(),
    );
    expect(screen.getAllByText(/associated with/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Linked Optimize rule")).toBeTruthy();
    expect(screen.getByText(/not causal proof/i)).toBeTruthy();
  });
});
