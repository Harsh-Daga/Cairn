import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FirstRun } from "@/components/common/FirstRun";
import type { WorkspaceResponse } from "@/lib/types";

const runAction = vi.fn();

vi.mock("@/lib/api", () => ({
  isStaticMode: vi.fn().mockReturnValue(false),
  runAction: (...args: unknown[]) => runAction(...args),
}));

function workspace(overrides: Partial<WorkspaceResponse> = {}): WorkspaceResponse {
  return {
    workspace_id: "ws-test",
    root_path: "/tmp/cairn-clean",
    name: "cairn-clean",
    adapters: [],
    health: {
      trace_count: 0,
      insight_count: 0,
      fts_available: false,
      adapter_warnings: [],
      human_label_agreement: { labeled_sessions: 0, agreements: 0, rate: null },
    },
    gauge: null,
    collection: null,
    resources: null,
    ...overrides,
  };
}

function renderFirstRun(value: WorkspaceResponse) {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>
        <FirstRun workspace={value} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("first-run workspace flow", () => {
  beforeEach(() => {
    runAction.mockReset();
    runAction.mockResolvedValue({ ok: true, job_id: "job-1" });
  });

  it("explains local storage and distinguishes no logs from a selected-range empty state", () => {
    renderFirstRun(workspace());
    expect(screen.getByRole("heading", { name: "No local agent logs found" })).toBeTruthy();
    expect(screen.getByText("/tmp/cairn-clean/.cairn/cairn.db")).toBeTruthy();
    expect(screen.getByText(/account-free, zero-telemetry/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sync now" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Rescan adapters" })).toBeTruthy();
  });

  it("surfaces parse failure and never offers automatic agent configuration", () => {
    renderFirstRun(
      workspace({
        adapters: [
          {
            source: "codex",
            streams: 1,
            cursor_updated_at: null,
            attempts: 2,
            fully_parsed: 0,
            degraded: 1,
            skipped: 1,
            parse_coverage: 0,
            unknown_fields: {},
            last_success_at: null,
            warning: true,
            issue_url: "https://example.invalid",
          },
        ],
      }),
    );
    expect(
      screen.getByRole("heading", { name: "Logs found, but parsing needs attention" }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View setup guide" }));
    expect(screen.getByText(/never edits agent or MCP configuration/)).toBeTruthy();
  });

  it("queues sync and creates demo data in a separate workspace", async () => {
    renderFirstRun(workspace());
    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));
    await waitFor(() => expect(runAction).toHaveBeenCalledWith("sync", {}));
    expect(await screen.findByText(/local job is queued/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Rescan adapters" }));
    await waitFor(() => expect(runAction).toHaveBeenCalledWith("workspace_scan", { force: true }));

    runAction.mockResolvedValueOnce({
      ok: true,
      result: { root: "/tmp/cairn-demo" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Load deterministic demo" }));
    expect(await screen.findByText('cairn ui --workspace "/tmp/cairn-demo"')).toBeTruthy();
    expect(screen.getByText(/cannot mix with your data/)).toBeTruthy();
    expect(screen.queryByText(/The local action completed/)).toBeNull();
    expect(screen.queryByText(/local job is queued/)).toBeNull();
  });

  it("offers approved local git exclude without editing shared gitignore", async () => {
    runAction.mockResolvedValueOnce({
      ok: true,
      result: {
        message: "Added .cairn/ to .git/info/exclude (local only; not shared .gitignore).",
      },
    });
    renderFirstRun(workspace());
    fireEvent.click(screen.getByRole("button", { name: "Approve local git exclude" }));
    await waitFor(() =>
      expect(runAction).toHaveBeenCalledWith("git_exclude_cairn", { approve: true }),
    );
    expect(await screen.findByText(/Added \.cairn\/ to \.git\/info\/exclude/)).toBeTruthy();
  });
});
