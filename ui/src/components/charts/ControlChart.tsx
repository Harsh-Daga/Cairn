import { LinePath, Line } from "@visx/shape";
import { scaleLinear } from "@visx/scale";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows } from "@visx/grid";
import { Group } from "@visx/group";
import { curveMonotoneX } from "@visx/curve";
import { chartColors, defaultMargin } from "./chartTheme";

export interface ControlChartProps {
  data: number[];
  mean?: number;
  ucl?: number;
  lcl?: number;
  width?: number;
  height?: number;
  className?: string;
}

export function ControlChart({
  data,
  mean,
  ucl,
  lcl,
  width = 400,
  height = 180,
  className,
}: ControlChartProps) {
  const margin = defaultMargin(8, 8, 28, 40);
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const computedMean = mean ?? data.reduce((a, b) => a + b, 0) / Math.max(data.length, 1);
  const sd =
    Math.sqrt(
      data.reduce((sum, v) => sum + (v - computedMean) ** 2, 0) / Math.max(data.length, 1),
    ) || 1;
  const upper = ucl ?? computedMean + 2 * sd;
  const lower = lcl ?? computedMean - 2 * sd;

  const yMin = Math.min(...data, lower);
  const yMax = Math.max(...data, upper);

  const xScale = scaleLinear({ domain: [0, Math.max(data.length - 1, 1)], range: [0, innerW] });
  const yScale = scaleLinear({ domain: [yMin, yMax], range: [innerH, 0], nice: true });

  return (
    <svg width={width} height={height} className={className} role="img" aria-label="Control chart">
      <Group left={margin.left} top={margin.top}>
        <GridRows scale={yScale} width={innerW} stroke={chartColors.grid} strokeOpacity={0.4} />
        <Line from={{ x: 0, y: yScale(upper) ?? 0 }} to={{ x: innerW, y: yScale(upper) ?? 0 }} stroke={chartColors.fillWarn} strokeDasharray="4 4" strokeWidth={1} />
        <Line from={{ x: 0, y: yScale(computedMean) ?? 0 }} to={{ x: innerW, y: yScale(computedMean) ?? 0 }} stroke={chartColors.muted} strokeWidth={1} />
        <Line from={{ x: 0, y: yScale(lower) ?? 0 }} to={{ x: innerW, y: yScale(lower) ?? 0 }} stroke={chartColors.fillWarn} strokeDasharray="4 4" strokeWidth={1} />
        <LinePath
          data={data}
          x={(_, i) => xScale(i) ?? 0}
          y={(d) => yScale(d) ?? 0}
          curve={curveMonotoneX}
          stroke={chartColors.stroke}
          strokeWidth={1.5}
          fill="none"
        />
        <AxisLeft scale={yScale} stroke={chartColors.axis} tickStroke={chartColors.axis} tickLabelProps={() => ({ fill: chartColors.muted, fontSize: 10, fontFamily: "var(--font-mono)" })} numTicks={4} />
        <AxisBottom top={innerH} scale={xScale} stroke={chartColors.axis} tickStroke={chartColors.axis} tickLabelProps={() => ({ fill: chartColors.muted, fontSize: 10, fontFamily: "var(--font-mono)" })} numTicks={4} />
      </Group>
    </svg>
  );
}
