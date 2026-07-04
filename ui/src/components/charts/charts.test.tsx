import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import {
  Sparkline,
  StackedArea,
  HorizontalBars,
  Radar,
  ControlChart,
  IntervalPlot,
  Gauge,
} from "./index";

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
      <IntervalPlot
        points={[{ label: "A", value: 5, low: 3, high: 7 }]}
        width={200}
        height={80}
      />,
    );
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("Gauge", () => {
    const { container } = render(<Gauge value={65} detail="650k / 1M" label="plan window · 5h" />);
    expect(container.querySelector('[role="meter"]')).toBeTruthy();
  });
});
