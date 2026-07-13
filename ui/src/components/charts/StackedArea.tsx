import { AreaStack } from "@visx/shape";
import { scaleLinear, scaleBand } from "@visx/scale";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows } from "@visx/grid";
import { Group } from "@visx/group";
import { useState } from "react";
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
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const active = activeIndex == null ? null : data[activeIndex];

  function updateActive(clientX: number, svg: SVGSVGElement) {
    const box = svg.getBoundingClientRect();
    const x = Math.max(0, Math.min(innerW, clientX - box.left - margin.left));
    const index = Math.round((x / Math.max(innerW, 1)) * Math.max(data.length - 1, 0));
    setActiveIndex(index);
  }

  return (
    <div className="relative max-w-full overflow-x-auto">
      {active ? (
        <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] text-cinder" aria-live="polite">
          <span className="text-bone">{String(active[xKey])}</span>
          {keys.map((key) => <span key={key}>{key}: {Number(active[key] ?? 0).toLocaleString()}</span>)}
        </div>
      ) : <p className="mb-2 font-mono text-[10px] text-cinder">Hover to inspect a point</p>}
    <svg
      width={width}
      height={height}
      className={`chart-entrance ${className ?? ""}`}
      role="img"
      aria-label="Stacked area chart; hover to inspect data points"
      onPointerMove={(event) => updateActive(event.clientX, event.currentTarget)}
      onPointerLeave={() => setActiveIndex(null)}
    >
      <defs>
        {keys.map((_, index) => (
          <pattern key={index} id={`cairn-area-dither-${index}`} width="6" height="6" patternUnits="userSpaceOnUse">
            <rect width="6" height="6" fill={seriesColor(index)} fillOpacity="0.34" />
            <circle cx="1.25" cy="1.25" r="0.9" fill={seriesColor(index)} />
            <circle cx="4.25" cy="4.25" r="0.9" fill={seriesColor(index)} />
          </pattern>
        ))}
      </defs>
      <Group left={margin.left} top={margin.top}>
        <GridRows scale={yScale} width={innerW} stroke={chartColors.grid} strokeOpacity={0.4} />
        <AreaStack
          keys={keys}
          data={data}
          x={(d) => xScale(String(d.data[xKey])) ?? 0}
          y0={(d) => yScale(d[0]) ?? 0}
          y1={(d) => yScale(d[1]) ?? 0}
          color={(_, i) => `url(#cairn-area-dither-${i})`}
        />
        {activeIndex != null ? (
          <line
            x1={(xScale(String(data[activeIndex]?.[xKey])) ?? 0) + xScale.bandwidth() / 2}
            x2={(xScale(String(data[activeIndex]?.[xKey])) ?? 0) + xScale.bandwidth() / 2}
            y1={0}
            y2={innerH}
            stroke={chartColors.text}
            strokeOpacity={0.45}
            strokeDasharray="3 3"
          />
        ) : null}
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
    </div>
  );
}
