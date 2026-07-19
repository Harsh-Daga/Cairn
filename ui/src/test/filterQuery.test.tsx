import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FilterQuery } from "@/components/common/FilterQuery";
import { FILTER_SPECS } from "@/lib/generated/filter-grammar";
import { privacySafeFilterQuery, privacySafeFilterUrl } from "@/lib/filterPrivacy";

describe("shared filter query UI", () => {
  it("uses generated operator metadata and exposes unavailable evidence filters", () => {
    expect(FILTER_SPECS.cost.example).toBe("cost:>1");
    expect(FILTER_SPECS.claim.available).toBe(false);
    expect(FILTER_SPECS.claim.unavailable_reason).toMatch(/not available/);
  });

  it("renders accessible chips/errors and commits chip removal", () => {
    const onChange = vi.fn();
    const onSubmit = vi.fn();
    render(
      <FilterQuery
        label="Session filter"
        value="cost:>1 claim:unsupported"
        onChange={onChange}
        onSubmit={onSubmit}
        placeholder="Filter"
        tokens={[
          {
            raw: "cost:>1",
            field: "cost",
            value: "1",
            comparison: "gt",
            available: true,
          },
        ]}
        errors={[
          {
            token: "claim:unsupported",
            message: "Claim-level verification receipts are not available yet.",
          },
        ]}
      />,
    );

    expect(screen.getByRole("alert").textContent).toMatch(/Claim-level/);
    fireEvent.click(screen.getByRole("button", { name: "Remove filter cost:>1" }));
    expect(onChange).toHaveBeenCalledWith("claim:unsupported");
    expect(onSubmit).toHaveBeenCalledWith("claim:unsupported");
  });

  it("excludes free text, relative files, and agent identifiers from copied URLs", () => {
    const tokens = [
      {
        raw: 'file:"private/customer.py"',
        field: "file" as const,
        value: "private/customer.py",
        comparison: "eq" as const,
        available: true,
      },
      {
        raw: "agent:customer-name",
        field: "agent" as const,
        value: "customer-name",
        comparison: "eq" as const,
        available: true,
      },
      {
        raw: "cost:>1",
        field: "cost" as const,
        value: "1",
        comparison: "gt" as const,
        available: true,
      },
    ];
    expect(privacySafeFilterQuery(tokens)).toBe("cost:>1");
    const copied = privacySafeFilterUrl(
      "http://127.0.0.1:8787/sessions?q=private+phrase&agent=customer-name",
      tokens,
    );
    expect(copied).not.toContain("private");
    expect(copied).not.toContain("customer");
    expect(copied).toContain("cost%3A%3E1");
  });
});
