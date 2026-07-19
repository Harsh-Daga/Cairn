import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import {
  Sparkline,
  StackedArea,
  HorizontalBars,
  Radar,
  ControlChart,
  IntervalPlot,
  Gauge,
  ChartFrame,
} from "./index";
import { aggregateOtherSeries } from "./chartTheme";

describe("chart kit smoke renders", () => {
  it("Sparkline", () => {
    const { container } = render(<Sparkline data={[1, 3, 2, 5, 4]} width={80} height={24} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("StackedArea", () => {
    const { container } = render(
      <StackedArea
        data={[
          { day: "Mon", a: 10, b: 5 },
          { day: "Tue", a: 8, b: 7 },
        ]}
        keys={["a", "b"]}
        xKey="day"
        width={200}
        height={120}
      />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("inspects stacked-area points with the keyboard", () => {
    const { container } = render(
      <StackedArea
        data={[
          { day: "Mon", cost: 10 },
          { day: "Tue", cost: 12 },
        ]}
        keys={["cost"]}
        xKey="day"
        width={200}
        height={120}
      />,
    );
    const chart = screen.getByRole("img", { name: /left and right arrow keys/i });
    fireEvent.focus(chart);
    expect(container.querySelector('[aria-live="polite"]')?.textContent).toContain("Mon");
    fireEvent.keyDown(chart, { key: "ArrowRight" });
    expect(container.querySelector('[aria-live="polite"]')?.textContent).toContain("Tue");
    fireEvent.keyDown(chart, { key: "Home" });
    expect(container.querySelector('[aria-live="polite"]')?.textContent).toContain("Mon");
  });

  it("HorizontalBars", () => {
    const { container } = render(
      <HorizontalBars
        items={[
          { label: "cache", value: 42 },
          { label: "retry", value: 18 },
        ]}
        width={200}
        height={100}
      />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("Radar", () => {
    const { container } = render(
      <Radar
        points={[
          { axis: "tools", value: 0.8 },
          { axis: "cost", value: 0.4 },
          { axis: "quality", value: 0.6 },
        ]}
        width={160}
        height={160}
      />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("ControlChart", () => {
    const { container } = render(
      <ControlChart data={[1.2, 1.0, 1.4, 0.9, 1.1]} width={200} height={100} />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("IntervalPlot", () => {
    const { container } = render(
      <IntervalPlot points={[{ label: "A", value: 5, low: 3, high: 7 }]} width={200} height={80} />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("Gauge", () => {
    const { container } = render(<Gauge value={65} detail="650k / 1M" label="plan window · 5h" />);
    expect(container.querySelector('[role="meter"]')).toBeTruthy();
  });

  it("ChartFrame exposes a sentence and equivalent table", () => {
    render(
      <ChartFrame
        title="Spend trend"
        summary="Spend rose from 10 to 12 dollars."
        rows={[
          { day: "Mon", spend: 10 },
          { day: "Tue", spend: 12 },
        ]}
        columns={[
          { key: "day", label: "Day", value: (row) => row.day },
          { key: "spend", label: "Spend", numeric: true, value: (row) => row.spend },
        ]}
      >
        <div aria-hidden="true">visual</div>
      </ChartFrame>,
    );
    expect(screen.getByText("Spend rose from 10 to 12 dollars.")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Spend trend data" })).toBeTruthy();
  });

  it("deterministically aggregates excess series as other", () => {
    const keys = ["a", "b", "c", "d", "e", "f", "g", "h"];
    const aggregated = aggregateOtherSeries(
      [{ day: "Mon", a: 1, b: 2, c: 3, d: 4, e: 5, f: 6, g: 7, h: 8 }],
      keys,
    );
    expect(aggregated.keys).toEqual(["a", "b", "c", "d", "e", "f", "other"]);
    expect(aggregated.data[0]?.other).toBe(15);
  });
});
