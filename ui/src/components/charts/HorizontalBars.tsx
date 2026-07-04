import { Bar } from "@visx/shape";
import { scaleBand, scaleLinear } from "@visx/scale";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { Group } from "@visx/group";
import { chartColors, defaultMargin } from "./chartTheme";

export interface HorizontalBarItem {
  label: string;
  value: number;
  color?: string;
}

export interface HorizontalBarsProps {
  items: HorizontalBarItem[];
  width?: number;
  height?: number;
  className?: string;
}

export function HorizontalBars({
  items,
  width = 320,
  height,
  className,
}: HorizontalBarsProps) {
  const rowHeight = 28;
  const computedHeight = height ?? Math.max(80, items.length * rowHeight + 40);
  const margin = defaultMargin(8, 16, 24, 80);
  const innerW = width - margin.left - margin.right;
  const innerH = computedHeight - margin.top - margin.bottom;

  const yScale = scaleBand({
    domain: items.map((i) => i.label),
    range: [0, innerH],
    padding: 0.25,
  });
  const xMax = Math.max(...items.map((i) => i.value), 1);
  const xScale = scaleLinear({ domain: [0, xMax], range: [0, innerW], nice: true });

  return (
    <svg width={width} height={computedHeight} className={className} role="img" aria-label="Horizontal bar chart">
      <Group left={margin.left} top={margin.top}>
        {items.map((item) => {
          const y = yScale(item.label) ?? 0;
          const barW = xScale(item.value) ?? 0;
          const barH = yScale.bandwidth();
          return (
            <Bar
              key={item.label}
              x={0}
              y={y}
              width={barW}
              height={barH}
              fill={item.color ?? chartColors.fill}
              rx={2}
            />
          );
        })}
        <AxisLeft
          scale={yScale}
          stroke={chartColors.axis}
          tickStroke={chartColors.axis}
          tickLabelProps={() => ({ fill: chartColors.text, fontSize: 10, fontFamily: "var(--font-mono)" })}
        />
        <AxisBottom
          top={innerH}
          scale={xScale}
          stroke={chartColors.axis}
          tickStroke={chartColors.axis}
          tickLabelProps={() => ({ fill: chartColors.muted, fontSize: 10, fontFamily: "var(--font-mono)" })}
          numTicks={4}
        />
      </Group>
    </svg>
  );
}
