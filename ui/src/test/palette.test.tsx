import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { CommandPalette } from "@/components/common/CommandPalette";
import { useUiStore } from "@/state/ui";
import axe from "axe-core";

vi.mock("@/lib/api", () => ({
  fetchActions: vi.fn().mockResolvedValue({
    actions: [
      {
        name: "sync",
        title: "Sync agent logs",
        category: "ingest",
        params_schema: {},
        async_job: true,
      },
      { name: "check", title: "Run CI gate", category: "ci", params_schema: {}, async_job: false },
    ],
  }),
  runAction: vi.fn().mockResolvedValue({ ok: true }),
  fetchTraces: vi.fn().mockResolvedValue({
    traces: [
      {
        trace_id: "trace-123",
        title: "Fix checkout race",
        source: "codex",
      },
    ],
    total: 1,
    limit: 5,
    offset: 0,
  }),
  isStaticMode: vi.fn().mockReturnValue(false),
}));

describe("command palette", () => {
  beforeEach(() => {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
    useUiStore.setState({ paletteOpen: true });
  });

  it("dispatches action from manifest", async () => {
    const { runAction } = await import("@/lib/api");
    const client = new QueryClient();
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <QueryClientProvider client={client}>
          <CommandPalette />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Sync agent logs")).toBeTruthy();
    });

    fireEvent.click(screen.getByText("Sync agent logs"));
    expect(runAction).toHaveBeenCalledWith("sync", {});
  });

  it("has no serious component-level accessibility violations", async () => {
    const client = new QueryClient();
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <QueryClientProvider client={client}>
          <CommandPalette />
        </QueryClientProvider>
      </MemoryRouter>,
    );
    await screen.findByText("Sync agent logs");
    const results = await axe.run(screen.getByRole("dialog", { name: "Command palette" }), {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag22aa"] },
      rules: { "color-contrast": { enabled: false } },
    });
    expect(
      results.violations.filter(
        (violation) => violation.impact === "serious" || violation.impact === "critical",
      ),
    ).toEqual([]);
  });

  it("searches sessions and applies theme and time-range commands", async () => {
    const client = new QueryClient();
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <QueryClientProvider client={client}>
          <CommandPalette />
        </QueryClientProvider>
      </MemoryRouter>,
    );
    const input = screen.getByRole("textbox", { name: "Search pages and actions" });
    fireEvent.change(input, { target: { value: "checkout" } });
    expect(await screen.findByText("Fix checkout race")).toBeTruthy();

    fireEvent.change(input, { target: { value: "theme dark" } });
    fireEvent.click(screen.getByRole("button", { name: "Use dark theme" }));
    expect(useUiStore.getState().themePreference).toBe("dark");

    act(() => useUiStore.setState({ paletteOpen: true }));
    const reopenedInput = await screen.findByRole("textbox", {
      name: "Search pages and actions",
    });
    fireEvent.change(reopenedInput, { target: { value: "time range 7d" } });
    fireEvent.click(screen.getByRole("button", { name: "Use 7d time range" }));
    expect(useUiStore.getState().timeRange).toBe("7d");
  });
});
