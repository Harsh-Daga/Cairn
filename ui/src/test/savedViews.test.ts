import { describe, expect, it, beforeEach } from "vitest";
import { DEFAULT_VIEW, deleteSavedView, loadSavedViews, saveCurrentView } from "@/lib/savedViews";

describe("savedViews", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("loads default view when storage is empty", () => {
    expect(loadSavedViews()).toEqual([DEFAULT_VIEW]);
  });

  it("saves and deletes custom views", () => {
    const params = new URLSearchParams({ source: "cursor", sort: "cost" });
    const saved = saveCurrentView("Cursor costly", params);
    expect(saved.some((view) => view.name === "Cursor costly")).toBe(true);
    const custom = saved.find((view) => view.name === "Cursor costly");
    expect(custom?.params).toEqual({ source: "cursor", sort: "cost" });
    const afterDelete = deleteSavedView(custom!.id);
    expect(afterDelete.some((view) => view.id === custom!.id)).toBe(false);
    expect(afterDelete.some((view) => view.id === "default")).toBe(true);
  });
});
