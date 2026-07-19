import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { fetchBudget, fetchHealth, fetchWorkspace, runAction } from "@/lib/api";
import { SettingsPage } from "@/pages/Settings";

vi.mock("@/lib/api", () => ({
  fetchWorkspace: vi.fn(),
  fetchHealth: vi.fn(),
  fetchBudget: vi.fn(),
  runAction: vi.fn(),
  isStaticMode: vi.fn(() => false),
}));

const workspace = {
  workspace_id: "ws",
  name: "demo",
  root_path: "/tmp/demo",
  adapters: [
    {
      source: "cursor",
      streams: 2,
      parse_coverage: 0.9,
      warning: null,
      last_success_at: "2026-07-01T00:00:00Z",
      cursor_updated_at: "2026-07-01T00:00:00Z",
    },
  ],
  health: {
    trace_count: 12,
    insight_count: 3,
    human_label_agreement: { labeled_sessions: 2, agreements: 1, rate: 0.5 },
  },
  collection: {
    mode: "efficient",
    label: "Efficient",
    auto_sync_active: true,
    watcher_enabled: true,
    refresh_enabled: true,
    poll_interval_sec: 30,
    refresh_interval_sec: 300,
    limitation: "Backend discovery only.",
    live_updates_note: "SSE is separate.",
  },
  resources: {
    disk: {
      cairn_dir: "/tmp/demo/.cairn",
      total_bytes: 2_097_152,
      database_bytes: 1_048_576,
      wal_bytes: 4096,
      exports_bytes: 0,
      backups_bytes: 0,
      regressions_bytes: 0,
    },
    budget: {
      status: "ok",
      soft_budget_bytes: 10_737_418_240,
      ratio: 0.0002,
      message: "Under soft budget.",
    },
    forecast: {
      window_days: 7,
      traces_ingested: 12,
      estimated_bytes_per_day: 1024,
      projected_total_in_30d: 3_000_000,
      kind: "descriptive",
      limitation: "Descriptive only.",
    },
    process_rss_bytes: 80_000_000,
    collection_mode: "efficient",
    limitation: "Inventory is local filesystem accounting.",
  },
};

describe("SettingsPage", () => {
  it("renders tabs, budget save, and rebuild confirmation dialog", async () => {
    vi.mocked(fetchWorkspace).mockResolvedValue(workspace as never);
    vi.mocked(fetchHealth).mockResolvedValue({ status: "ok", version: "1.1.1" });
    vi.mocked(fetchBudget).mockResolvedValue({
      timezone: "UTC",
      month_start: "2026-07-01T00:00:00+00:00",
      month_end: "2026-08-01T00:00:00+00:00",
      now: "2026-07-18T00:00:00+00:00",
      monthly_limit_usd: 100,
      weekly_limit_usd: null,
      daily_limit_usd: null,
      month_spend_usd: 12,
      week_spend_usd: 4,
      day_spend_usd: 1,
      observed_active_days: 8,
      calendar_days_elapsed: 18,
      days_in_month: 31,
      projection_state: "available",
      linear_projected_usd: 20.7,
      trailing_7d_projected_usd: 17.7,
      projected_overrun_date: null,
      budget_state: "healthy",
      explanation: "Measured spend is within configured ceilings.",
      agent_shares: [],
      model_shares: [{ key: "gpt-test", spend_usd: 12, share_pct: 100, sessions: 8 }],
      ledger: {
        conclusion: "Measured spend is within configured ceilings.",
        budget_state: "healthy",
        projection_state: "available",
        next_action: "Keep monitoring burn on Overview",
        next_action_href: "/",
        limitation: "Projections are descriptive extrapolations.",
      },
      limitations: ["Projections are descriptive extrapolations."],
    } as never);
    vi.mocked(runAction).mockImplementation(async (name, params = {}) => {
      if (name === "config_set" && params.operation === "list") {
        return {
          ok: true,
          result: {
            values: [
              {
                key: "budgets.monthly_usd",
                value: 100,
                source: "workspace",
                secret: false,
              },
              { key: "mcp.client", value: "cursor", source: "default", secret: false },
            ],
          },
        };
      }
      return { ok: true, result: {} };
    });

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <SettingsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText("demo")).toBeTruthy());
    expect(screen.getByRole("tab", { name: "budget" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Privacy & Network" })).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "budget" }));
    await waitFor(() => expect(screen.getByDisplayValue("100")).toBeTruthy());
    await waitFor(() => expect(screen.getByText(/Burn healthy/i)).toBeTruthy());
    fireEvent.click(screen.getAllByRole("button", { name: "Save" })[0]!);
    await waitFor(() =>
      expect(runAction).toHaveBeenCalledWith(
        "config_set",
        expect.objectContaining({
          operation: "set",
          key: "budgets.monthly_usd",
          value: "100",
        }),
      ),
    );

    fireEvent.click(screen.getByRole("tab", { name: "Resource & Privacy" }));
    expect(screen.getByText(/Resource & Privacy Center/i)).toBeTruthy();
    expect(screen.getByText(/Under soft budget/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Dry-run cleanup plan" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Rebuild views" }));
    expect(screen.getByRole("dialog", { name: "Rebuild derived views" })).toBeTruthy();
    expect((screen.getByRole("button", { name: "Rebuild" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "rebuild" } });
    expect((screen.getByRole("button", { name: "Rebuild" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
    vi.mocked(runAction).mockResolvedValueOnce({ ok: true, result: { recomputed: 1 } });
    fireEvent.click(screen.getByRole("button", { name: "Rebuild" }));
    await waitFor(() => expect(runAction).toHaveBeenCalledWith("rebuild_view", { view: "all" }));
  });
});
