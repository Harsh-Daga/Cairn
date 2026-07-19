import { AreaStack, LinePath } from "@visx/shape";
import { scaleLinear, scaleBand } from "@visx/scale";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows } from "@visx/grid";
import { Group } from "@visx/group";
import { useId, useState } from "react";
import { curveMonotoneX } from "@visx/curve";
import { formatNumber } from "@/lib/format";
import { aggregateOtherSeries, chartColors, defaultMargin, seriesColor } from "./chartTheme";

export interface StackedAreaProps {
  data: Record<string, number | string>[];
  keys: string[];
  xKey: string;
  width?: number;
  height?: number;
  className?: string;
  annotations?: ReadonlyArray<{ x: string; label: string }>;
}

export function StackedArea({
  data,
  keys,
  xKey,
  width = 400,
  height = 200,
  className,
  annotations = [],
}: StackedAreaProps) {
  const definitionId = useId().replace(/:/g, "");
  const visible = aggregateOtherSeries(data, keys);
  const visibleData = visible.data;
  const visibleKeys = visible.keys;
  const margin = defaultMargin(36, 18, 30, 46);
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const xScale = scaleBand({
    domain: visibleData.map((d) => String(d[xKey])),
    range: [0, innerW],
    padding: 0.2,
  });

  const yMax = Math.max(
    ...visibleData.map((d) => visibleKeys.reduce((sum, k) => sum + Number(d[k] ?? 0), 0)),
    1,
  );
  const yScale = scaleLinear({ domain: [0, yMax], range: [innerH, 0], nice: true });
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const active = activeIndex == null ? null : visibleData[activeIndex];

  function updateActive(clientX: number, svg: SVGSVGElement) {
    const box = svg.getBoundingClientRect();
    const x = Math.max(0, Math.min(innerW, clientX - box.left - margin.left));
    const index = Math.round((x / Math.max(innerW, 1)) * Math.max(visibleData.length - 1, 0));
    setActiveIndex(index);
  }

  function inspectByKeyboard(key: string) {
    if (visibleData.length === 0) return;
    if (key === "Home") setActiveIndex(0);
    if (key === "End") setActiveIndex(visibleData.length - 1);
    if (key === "ArrowLeft" || key === "ArrowRight") {
      const direction = key === "ArrowRight" ? 1 : -1;
      setActiveIndex((current) =>
        Math.max(0, Math.min(visibleData.length - 1, (current ?? 0) + direction)),
      );
    }
  }

  return (
    <div className="relative w-full">
      {active ? (
        <div
          className="pointer-events-none absolute right-2 top-0 z-10 flex items-center gap-3 rounded-sm border border-quartz-vein/80 bg-anthracite/90 px-3 py-2 font-mono text-[10px] shadow-stone backdrop-blur"
          aria-live="polite"
        >
          <span className="text-cinder">{String(active[xKey])}</span>
          {visibleKeys.map((key) => (
            <span key={key} className="text-bone">
              {key}{" "}
              <strong className="font-medium text-patina">
                {formatNumber(Number(active[key] ?? 0))}
              </strong>
            </span>
          ))}
        </div>
      ) : null}
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMinYMid meet"
        className={`chart-entrance ${className ?? ""}`}
        role="img"
        aria-label="Stacked area chart. Use left and right arrow keys to inspect data points."
        tabIndex={visibleData.length > 0 ? 0 : -1}
        onFocus={() => setActiveIndex((current) => current ?? 0)}
        onBlur={() => setActiveIndex(null)}
        onKeyDown={(event) => {
          if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
            event.preventDefault();
            inspectByKeyboard(event.key);
          }
        }}
        onPointerMove={(event) => updateActive(event.clientX, event.currentTarget)}
        onPointerLeave={() => setActiveIndex(null)}
      >
        <defs>
          {visibleKeys.map((_, index) => (
            <pattern
              key={index}
              id={`${definitionId}-area-dither-${index}`}
              width="5"
              height="5"
              patternUnits="userSpaceOnUse"
            >
              <rect width="5" height="5" fill={seriesColor(index)} fillOpacity="0.12" />
              <circle cx="1" cy="1" r="0.7" fill={seriesColor(index)} fillOpacity="0.76" />
            </pattern>
          ))}
          <filter id={`${definitionId}-signal-glow`} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <Group left={margin.left} top={margin.top}>
          <GridRows scale={yScale} width={innerW} stroke={chartColors.grid} strokeOpacity={0.4} />
          <AreaStack
            keys={visibleKeys}
            data={visibleData}
            x={(d) => xScale(String(d.data[xKey])) ?? 0}
            y0={(d) => yScale(d[0]) ?? 0}
            y1={(d) => yScale(d[1]) ?? 0}
            color={(_, i) => `url(#${definitionId}-area-dither-${i})`}
            curve={curveMonotoneX}
          />
          {visibleKeys.map((key, keyIndex) => (
            <LinePath
              key={key}
              data={visibleData}
              x={(row) => (xScale(String(row[xKey])) ?? 0) + xScale.bandwidth() / 2}
              y={(row) =>
                yScale(
                  visibleKeys
                    .slice(0, keyIndex + 1)
                    .reduce((sum, item) => sum + Number(row[item] ?? 0), 0),
                ) ?? 0
              }
              curve={curveMonotoneX}
              stroke={seriesColor(keyIndex)}
              strokeWidth={2}
              strokeLinecap="round"
              fill="none"
              filter={`url(#${definitionId}-signal-glow)`}
            />
          ))}
          {annotations.map((annotation) => {
            const x = xScale(annotation.x);
            if (x == null) return null;
            const center = x + xScale.bandwidth() / 2;
            return (
              <g key={`${annotation.x}-${annotation.label}`}>
                <title>{annotation.label}</title>
                <line
                  x1={center}
                  x2={center}
                  y1={0}
                  y2={innerH}
                  stroke="var(--ochre)"
                  strokeWidth={2}
                  strokeDasharray="2 3"
                />
                <circle cx={center} cy={3} r={3} fill="var(--ochre)" />
              </g>
            );
          })}
          {activeIndex != null ? (
            <>
              <line
                x1={
                  (xScale(String(visibleData[activeIndex]?.[xKey])) ?? 0) + xScale.bandwidth() / 2
                }
                x2={
                  (xScale(String(visibleData[activeIndex]?.[xKey])) ?? 0) + xScale.bandwidth() / 2
                }
                y1={0}
                y2={innerH}
                stroke={chartColors.text}
                strokeOpacity={0.3}
                strokeDasharray="3 4"
              />
              <circle
                cx={
                  (xScale(String(visibleData[activeIndex]?.[xKey])) ?? 0) + xScale.bandwidth() / 2
                }
                cy={
                  yScale(
                    visibleKeys.reduce(
                      (sum, key) => sum + Number(visibleData[activeIndex]?.[key] ?? 0),
                      0,
                    ),
                  ) ?? 0
                }
                r={4}
                fill="var(--anthracite)"
                stroke="var(--patina)"
                strokeWidth={2}
              />
            </>
          ) : null}
          <AxisLeft
            scale={yScale}
            hideAxisLine
            hideTicks
            tickLabelProps={() => ({
              fill: chartColors.muted,
              fontSize: 10,
              fontFamily: "var(--font-mono)",
              dx: -6,
            })}
            numTicks={4}
          />
          <AxisBottom
            top={innerH}
            scale={xScale}
            stroke={chartColors.grid}
            tickStroke={chartColors.grid}
            tickLabelProps={() => ({
              fill: chartColors.muted,
              fontSize: 10,
              fontFamily: "var(--font-mono)",
            })}
          />
        </Group>
      </svg>
    </div>
  );
}
