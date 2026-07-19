import { Bar, Line } from "@visx/shape";
import { scaleBand, scaleLinear } from "@visx/scale";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { Group } from "@visx/group";
import { chartColors, defaultMargin } from "./chartTheme";

export interface IntervalPoint {
  label: string;
  value: number;
  low: number;
  high: number;
}

export interface IntervalPlotProps {
  points: IntervalPoint[];
  width?: number;
  height?: number;
  className?: string;
}

export function IntervalPlot({ points, width = 360, height = 200, className }: IntervalPlotProps) {
  const margin = defaultMargin(8, 16, 28, 48);
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const yScale = scaleBand({
    domain: points.map((p) => p.label),
    range: [0, innerH],
    padding: 0.35,
  });
  const xMin = Math.min(...points.map((p) => p.low));
  const xMax = Math.max(...points.map((p) => p.high));
  const xScale = scaleLinear({ domain: [xMin, xMax], range: [0, innerW], nice: true });

  return (
    <svg width={width} height={height} className={className} role="img" aria-label="Interval plot">
      <Group left={margin.left} top={margin.top}>
        {points.map((p) => {
          const y = (yScale(p.label) ?? 0) + yScale.bandwidth() / 2;
          const x0 = xScale(p.low) ?? 0;
          const x1 = xScale(p.high) ?? 0;
          const xm = xScale(p.value) ?? 0;
          return (
            <Group key={p.label}>
              <Line
                from={{ x: x0, y }}
                to={{ x: x1, y }}
                stroke={chartColors.muted}
                strokeWidth={2}
              />
              <Line
                from={{ x: x0, y: y - 4 }}
                to={{ x: x0, y: y + 4 }}
                stroke={chartColors.muted}
                strokeWidth={1.5}
              />
              <Line
                from={{ x: x1, y: y - 4 }}
                to={{ x: x1, y: y + 4 }}
                stroke={chartColors.muted}
                strokeWidth={1.5}
              />
              <Bar x={xm - 3} y={y - 6} width={6} height={12} fill={chartColors.fill} rx={1} />
            </Group>
          );
        })}
        <AxisLeft
          scale={yScale}
          stroke={chartColors.axis}
          tickStroke={chartColors.axis}
          tickLabelProps={() => ({
            fill: chartColors.text,
            fontSize: 10,
            fontFamily: "var(--font-mono)",
          })}
        />
        <AxisBottom
          top={innerH}
          scale={xScale}
          stroke={chartColors.axis}
          tickStroke={chartColors.axis}
          tickLabelProps={() => ({
            fill: chartColors.muted,
            fontSize: 10,
            fontFamily: "var(--font-mono)",
          })}
          numTicks={4}
        />
      </Group>
    </svg>
  );
}
