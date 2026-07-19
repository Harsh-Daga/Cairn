import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchJson, setHumanLabel } from "@/lib/api";

afterEach(() => {
  delete window.__CAIRN_STATIC__;
  delete window.__CAIRN_STATIC_DATA__;
  vi.unstubAllGlobals();
});

describe("static snapshot API", () => {
  it("reads embedded data without a file-URL network request", async () => {
    window.__CAIRN_STATIC__ = true;
    window.__CAIRN_STATIC_DATA__ = { "./api/health.json": { status: "ok" } };
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchJson<{ status: string }>("/health")).resolves.toEqual({ status: "ok" });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("persists a human session label with an optional note", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ trace_id: "t1", label: "down", note: "Regressed" }), {
        status: 200,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await setHumanLabel("t1", "down", "Regressed");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/traces/t1/human-label",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ label: "down", note: "Regressed" }),
      }),
    );
  });

  it("explains uncaptured static filters instead of implying a live API failure", async () => {
    window.__CAIRN_STATIC__ = true;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("missing", { status: 404 })));

    await expect(fetchJson("/traces?days=30&offset=50")).rejects.toThrow(
      "static snapshot does not include",
    );
  });

  it("rejects static mutations before fetch", async () => {
    window.__CAIRN_STATIC__ = true;
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(setHumanLabel("t1", "up")).rejects.toThrow("read-only static snapshot");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
