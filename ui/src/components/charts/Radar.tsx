import { scaleLinear } from "@visx/scale";
import { Group } from "@visx/group";
import { chartColors, seriesColor } from "./chartTheme";

export interface RadarPoint {
  axis: string;
  value: number;
}

export interface RadarProps {
  points: RadarPoint[];
  maxValue?: number;
  width?: number;
  height?: number;
  className?: string;
}

export function Radar({ points, maxValue, width = 240, height = 240, className }: RadarProps) {
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) / 2 - 24;
  const max = maxValue ?? Math.max(...points.map((p) => p.value), 1);
  const angleStep = (Math.PI * 2) / Math.max(points.length, 1);

  const radialScale = scaleLinear({ domain: [0, max], range: [0, radius] });
  const rings = [0.25, 0.5, 0.75, 1];

  const polygon = points.map((p, i) => {
    const angle = i * angleStep - Math.PI / 2;
    const r = radialScale(p.value) ?? 0;
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  });

  return (
    <svg width={width} height={height} className={className} role="img" aria-label="Radar chart">
      <Group>
        {rings.map((ring) => (
          <circle
            key={ring}
            cx={cx}
            cy={cy}
            r={radius * ring}
            fill="none"
            stroke={chartColors.grid}
            strokeOpacity={0.5}
            strokeWidth={1}
          />
        ))}
        <polygon
          points={polygon.map((p) => `${p.x},${p.y}`).join(" ")}
          fill={seriesColor(0)}
          fillOpacity={0.25}
          stroke={seriesColor(0)}
          strokeWidth={1.5}
        />
        {points.map((p, i) => {
          const angle = i * angleStep - Math.PI / 2;
          const lx = cx + (radius + 12) * Math.cos(angle);
          const ly = cy + (radius + 12) * Math.sin(angle);
          return (
            <text
              key={p.axis}
              x={lx}
              y={ly}
              textAnchor="middle"
              dominantBaseline="middle"
              fill={chartColors.muted}
              fontSize={10}
              fontFamily="var(--font-mono)"
            >
              {p.axis}
            </text>
          );
        })}
      </Group>
    </svg>
  );
}
