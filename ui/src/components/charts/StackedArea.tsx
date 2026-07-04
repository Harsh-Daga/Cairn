import { AreaStack } from "@visx/shape";
import { scaleLinear, scaleBand } from "@visx/scale";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows } from "@visx/grid";
import { Group } from "@visx/group";
import { chartColors, defaultMargin, seriesColor } from "./chartTheme";

export interface StackedAreaProps {
  data: Record<string, number | string>[];
  keys: string[];
  xKey: string;
  width?: number;
  height?: number;
  className?: string;
}

export function StackedArea({
  data,
  keys,
  xKey,
  width = 400,
  height = 200,
  className,
}: StackedAreaProps) {
  const margin = defaultMargin(8, 8, 28, 40);
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const xScale = scaleBand({
    domain: data.map((d) => String(d[xKey])),
    range: [0, innerW],
    padding: 0.2,
  });

  const yMax = Math.max(
    ...data.map((d) => keys.reduce((sum, k) => sum + Number(d[k] ?? 0), 0)),
    1,
  );
  const yScale = scaleLinear({ domain: [0, yMax], range: [innerH, 0], nice: true });

  return (
    <svg width={width} height={height} className={className} role="img" aria-label="Stacked area chart">
      <Group left={margin.left} top={margin.top}>
        <GridRows scale={yScale} width={innerW} stroke={chartColors.grid} strokeOpacity={0.4} />
        <AreaStack
          keys={keys}
          data={data}
          x={(d) => xScale(String(d.data[xKey])) ?? 0}
          y0={(d) => yScale(d[0]) ?? 0}
          y1={(d) => yScale(d[1]) ?? 0}
          color={(_, i) => seriesColor(i)}
        />
        <AxisLeft scale={yScale} stroke={chartColors.axis} tickStroke={chartColors.axis} tickLabelProps={() => ({ fill: chartColors.muted, fontSize: 10, fontFamily: "var(--font-mono)" })} numTicks={4} />
        <AxisBottom
          top={innerH}
          scale={xScale}
          stroke={chartColors.axis}
          tickStroke={chartColors.axis}
          tickLabelProps={() => ({ fill: chartColors.muted, fontSize: 10, fontFamily: "var(--font-mono)" })}
        />
      </Group>
    </svg>
  );
}
