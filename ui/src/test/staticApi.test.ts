import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchJson } from "@/lib/api";

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
});
