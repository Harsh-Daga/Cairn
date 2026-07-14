import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchJson, setHumanLabel } from "@/lib/api";

afterEach(() => {
  delete window.__CAIRN_STATIC__;
  vi.unstubAllGlobals();
});

describe("static snapshot API", () => {
  it("uses a relative API path for project-site hosting", async () => {
    window.__CAIRN_STATIC__ = true;
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchJson<{ status: string }>("/health");

    expect(fetchMock).toHaveBeenCalledWith("./api/health.json", undefined);
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
});
