import { AreaClosed, LinePath } from "@visx/shape";
import { scaleLinear } from "@visx/scale";
import { curveMonotoneX } from "@visx/curve";
import { chartColors } from "./chartTheme";
import { useId } from "react";

export interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  strokeWidth?: number;
  className?: string;
}

export function Sparkline({
  data,
  width = 120,
  height = 32,
  color = chartColors.stroke,
  strokeWidth = 1.5,
  className,
}: SparklineProps) {
  const gradientId = useId().replace(/:/g, "");
  if (data.length < 2) {
    return (
      <svg width={width} height={height} className={className} aria-hidden="true">
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke={chartColors.grid}
          strokeWidth={1}
        />
      </svg>
    );
  }

  const xScale = scaleLinear({
    domain: [0, data.length - 1],
    range: [0, width],
  });
  const yScale = scaleLinear({
    domain: [Math.min(...data), Math.max(...data)],
    range: [height - 2, 2],
    nice: true,
  });

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.32" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <AreaClosed
        data={data}
        x={(_, i) => xScale(i) ?? 0}
        y={(d) => yScale(d) ?? 0}
        yScale={yScale}
        curve={curveMonotoneX}
        fill={`url(#${gradientId})`}
      />
      <LinePath
        data={data}
        x={(_, i) => xScale(i) ?? 0}
        y={(d) => yScale(d) ?? 0}
        curve={curveMonotoneX}
        stroke={color}
        strokeWidth={strokeWidth + 0.25}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}
