import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  Badge,
  Breadcrumbs,
  Card,
  ConfidenceInterval,
  CopyButton,
  DataTable,
  EmptyState,
  ErrorBoundary,
  EstimateBadge,
  InlineError,
  MetricHelp,
  SegmentedControl,
  Skeleton,
  Stat,
  TimeRangePicker,
} from ".";
import { MemoryRouter } from "react-router-dom";

beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

describe("shared UI primitives", () => {
  it("exposes metric meaning, estimates, deltas, and confidence as text", () => {
    render(
      <Card title="Spend" metricHelp={{ definition: "Local model cost." }}>
        <div className="p-4">
          <Stat label="Cost" value="$12" delta="4%" deltaDirection="up" estimated />
          <ConfidenceInterval low={8} estimate={12} high={16} format={(value) => `$${value}`} />
          <EstimateBadge />
        </div>
      </Card>,
    );
    expect(screen.getByText("Spend")).toBeTruthy();
    expect(
      screen.getByText(
        (_content, element) => element?.tagName === "P" && element.textContent === "$12 estimated",
      ),
    ).toBeTruthy();
    expect(screen.getByLabelText(/Estimate \$12; confidence interval \$8 to \$16/)).toBeTruthy();
  });

  it("renders analyze-page Stat card grammar when detail is provided", () => {
    render(
      <Stat
        label="Invocations"
        value="42"
        detail="Across tool_call spans in range"
        estimated
        help={{ definition: "Count of tool calls." }}
      />,
    );
    expect(screen.getByText("Invocations")).toBeTruthy();
    expect(screen.getByText("42")).toBeTruthy();
    expect(screen.getByText("Across tool_call spans in range")).toBeTruthy();
    expect(screen.getByText("Estimated")).toBeTruthy();
  });

  it("copies only after an explicit user action and announces completion", async () => {
    render(<CopyButton value="local value" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("local value");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeTruthy();
  });

  it("renders named feedback, badges, breadcrumbs, and metric help", () => {
    const change = vi.fn();
    render(
      <MemoryRouter>
        <Breadcrumbs items={[{ label: "Sessions", to: "/sessions" }, { label: "Trace" }]} />
        <EmptyState title="No data" detail="Sync a workspace." />
        <InlineError message="Could not load." />
        <Skeleton label="Loading sessions" />
        <Badge tone="critical">Critical</Badge>
        <MetricHelp definition="Definition" calculation="Sum rows" />
        <SegmentedControl
          label="Mode"
          value="one"
          options={[
            { value: "one", label: "One" },
            { value: "two", label: "Two" },
          ]}
          onChange={change}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeTruthy();
    expect(screen.getByText("Trace").getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("alert").textContent).toContain("Could not load");
    expect(screen.getByRole("status", { name: "Loading sessions" })).toBeTruthy();
    expect(screen.getByText("Critical")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Two" }));
    expect(change).toHaveBeenCalledWith("two");
  });

  it("maps rendering failures to local boundary state", () => {
    const error = new Error("private local content");
    expect(ErrorBoundary.getDerivedStateFromError(error)).toEqual({ error });
  });

  it("has no component-level axe violations", async () => {
    const { container } = render(
      <MemoryRouter>
        <Card title="Summary">
          <div className="p-4">
            <Stat label="Sessions" value="12" />
            <InlineError message="Example error" />
            <CopyButton value="bounded" />
          </div>
        </Card>
      </MemoryRouter>,
    );
    const results = await axe.run(container, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag22aa"] },
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });

  it("announces table sorting, selection, keyboard movement, and server pages", () => {
    const select = vi.fn();
    const sort = vi.fn();
    const page = vi.fn();
    render(
      <DataTable
        label="Example rows"
        columns={[
          { key: "name", header: "Name", sortable: true, cell: (row) => row.name },
          { key: "value", header: "Value", numeric: true, cell: (row) => row.value },
        ]}
        rows={[
          { id: "a", name: "Alpha", value: 1 },
          { id: "b", name: "Beta", value: 2 },
        ]}
        rowKey={(row) => row.id}
        sort={{ key: "name", direction: "ascending" }}
        onSort={sort}
        page={1}
        pageCount={2}
        totalRows={4}
        onPageChange={page}
        selectedKey="a"
        onSelect={select}
      />,
    );
    expect(screen.getByRole("columnheader", { name: /Name/ }).getAttribute("aria-sort")).toBe(
      "ascending",
    );
    fireEvent.click(screen.getByRole("button", { name: /Name/ }));
    expect(sort).toHaveBeenCalledWith("name");
    fireEvent.keyDown(screen.getByText("Alpha").closest("tr")!, { key: "j" });
    expect(select).toHaveBeenCalledWith({ id: "b", name: "Beta", value: 2 });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(page).toHaveBeenCalledWith(2);
  });

  it("validates and emits custom time ranges", () => {
    const preset = vi.fn();
    const custom = vi.fn();
    render(<TimeRangePicker value="30d" onPreset={preset} onCustom={custom} />);
    fireEvent.click(screen.getByRole("button", { name: "7d" }));
    expect(preset).toHaveBeenCalledWith("7d");
    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    const start = screen.getByLabelText("Start");
    fireEvent.change(start, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByRole("alert").textContent).toContain("Choose a start");
    expect(custom).not.toHaveBeenCalled();
  });

  it("virtualizes large bounded table pages while retaining table semantics", async () => {
    const rows = Array.from({ length: 150 }, (_value, index) => ({
      id: String(index),
      name: `Row ${index}`,
    }));
    render(
      <DataTable
        label="Virtual rows"
        columns={[{ key: "name", header: "Name", cell: (row) => row.name }]}
        rows={rows}
        rowKey={(row) => row.id}
        virtualizeAbove={10}
      />,
    );
    await waitFor(() => expect(screen.getAllByRole("row").length).toBeGreaterThan(2));
    expect(screen.getAllByRole("row").length).toBeLessThan(rows.length);
    expect(screen.getByRole("table", { name: "Virtual rows" })).toBeTruthy();
  });
});
