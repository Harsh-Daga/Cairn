import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { useGlobalShortcuts } from "@/hooks/useGlobalShortcuts";
import { PageShell } from "@/components/common/PageShell";
import { NAVIGATION_GROUPS, NAVIGATION_ITEMS } from "@/lib/navigation";
import { useUiStore } from "@/state/ui";

function ShortcutHarness() {
  useGlobalShortcuts();
  const location = useLocation();
  return <output aria-label="Current path">{location.pathname}</output>;
}

describe("application shell navigation", () => {
  beforeEach(() => {
    useUiStore.setState({ paletteOpen: false, shortcutsOpen: false, timeRange: "30d" });
  });

  it("keeps the canonical groups and core routes in one registry", () => {
    expect(NAVIGATION_GROUPS).toEqual(["Monitor", "Analyze", "Act", "Utilities"]);
    expect(
      NAVIGATION_ITEMS.filter((item) => item.group === "Monitor").map((item) => item.label),
    ).toEqual(["Overview", "Live", "Sessions"]);
    expect(NAVIGATION_ITEMS.some((item) => item.label === "Search")).toBe(true);
    expect(NAVIGATION_ITEMS.some((item) => item.label === "Settings")).toBe(true);
  });

  it("supports go chords and slash search without stealing input keystrokes", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <ShortcutHarness />
        <input aria-label="Editor" />
      </MemoryRouter>,
    );
    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "c" });
    expect(screen.getByLabelText("Current path").textContent).toBe("/context");

    fireEvent.keyDown(window, { key: "/" });
    expect(useUiStore.getState().paletteOpen).toBe(true);

    useUiStore.setState({ paletteOpen: false });
    const editor = screen.getByRole("textbox", { name: "Editor" });
    fireEvent.keyDown(editor, { key: "/" });
    expect(useUiStore.getState().paletteOpen).toBe(false);
  });

  it("adds stable breadcrumbs to session detail routes", () => {
    render(
      <MemoryRouter initialEntries={["/sessions/trace-123"]}>
        <PageShell title="Session detail" question="Inspect the trace." />
      </MemoryRouter>,
    );
    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(breadcrumb.textContent).toContain("Sessions");
    expect(breadcrumb.textContent).toContain("Session detail");
  });
});
