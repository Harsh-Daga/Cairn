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
  const margin = defaultMargin(8, 64, 24, 124);
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
    <svg
      width="100%"
      height={computedHeight}
      viewBox={`0 0 ${width} ${computedHeight}`}
      preserveAspectRatio="xMinYMid meet"
      className={`chart-entrance ${className ?? ""}`}
      role="img"
      aria-label="Horizontal bar chart"
    >
      <defs>
        <linearGradient id="horizontal-bar-signal" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--copper)" stopOpacity="0.58" />
          <stop offset="100%" stopColor="var(--patina)" stopOpacity="0.96" />
        </linearGradient>
      </defs>
      <Group left={margin.left} top={margin.top}>
        {items.map((item) => {
          const y = yScale(item.label) ?? 0;
          const barW = xScale(item.value) ?? 0;
          const barH = yScale.bandwidth();
          return <Group key={item.label}>
            <Bar x={0} y={y} width={innerW} height={barH} fill="var(--granite)" fillOpacity={0.42} rx={4} />
            <Bar x={0} y={y} width={barW} height={barH} fill={item.color ?? "url(#horizontal-bar-signal)"} rx={4} />
            <text x={innerW + 10} y={y + barH / 2} dominantBaseline="middle" fill={chartColors.text} fontSize={10} fontFamily="var(--font-mono)">
              {item.value.toLocaleString()}
            </text>
          </Group>;
        })}
        <AxisLeft
          scale={yScale}
          hideAxisLine
          hideTicks
          tickLabelProps={() => ({ fill: chartColors.text, fontSize: 10, fontFamily: "var(--font-ui)", textAnchor: "end", dx: -8 })}
        />
        <AxisBottom
          top={innerH}
          scale={xScale}
          stroke={chartColors.grid}
          tickStroke={chartColors.grid}
          tickLabelProps={() => ({ fill: chartColors.muted, fontSize: 10, fontFamily: "var(--font-mono)" })}
          numTicks={4}
        />
      </Group>
    </svg>
  );
}
