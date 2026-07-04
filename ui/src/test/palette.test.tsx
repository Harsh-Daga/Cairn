import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CommandPalette } from "@/components/common/CommandPalette";
import { useUiStore } from "@/state/ui";

vi.mock("@/lib/api", () => ({
  fetchActions: vi.fn().mockResolvedValue({
    actions: [
      { name: "sync", title: "Sync agent logs", category: "ingest", params_schema: {}, async_job: true },
      { name: "check", title: "Run CI gate", category: "ci", params_schema: {}, async_job: false },
    ],
  }),
  runAction: vi.fn().mockResolvedValue({ ok: true }),
}));

describe("command palette", () => {
  beforeEach(() => {
    useUiStore.setState({ paletteOpen: true });
  });

  it("dispatches action from manifest", async () => {
    const { runAction } = await import("@/lib/api");
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <CommandPalette />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Sync agent logs")).toBeTruthy();
    });

    fireEvent.click(screen.getByText("Sync agent logs"));
    expect(runAction).toHaveBeenCalledWith("sync");
  });
});
