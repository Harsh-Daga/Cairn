import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AdapterWarningBanner } from "@/components/common/AdapterHealthBanner";

describe("adapter parse health banner", () => {
  it("shows an honest warning and prefilled issue action", () => {
    render(
      <AdapterWarningBanner
        warnings={[
          {
            adapter_id: "codex",
            message: "codex log format may have changed; numbers may be incomplete.",
            issue_url: "https://github.com/Harsh-Daga/Cairn/issues/new?title=codex",
          },
        ]}
      />,
    );
    expect(screen.getByRole("alert").textContent).toContain("numbers may be incomplete");
    expect(screen.getByRole("link").getAttribute("href")).toContain("issues/new");
  });
});
