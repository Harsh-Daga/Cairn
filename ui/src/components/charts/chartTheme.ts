/** Shared chart tokens — reads Cairn theme CSS variables. */

export const CHART_SERIES = [
  "var(--s-system)",
  "var(--s-tool)",
  "var(--s-result)",
  "var(--s-cache)",
  "var(--s-assistant)",
  "var(--s-retrieved)",
  "var(--s-error)",
  "var(--s-good)",
] as const;

export function seriesColor(index: number): string {
  const i = index % CHART_SERIES.length;
  return CHART_SERIES[i] as string;
}

export const chartColors = {
  axis: "var(--cinder)",
  grid: "var(--quartz-vein)",
  fill: "var(--copper)",
  fillWarn: "var(--cinnabar)",
  fillGood: "var(--malachite)",
  stroke: "var(--copper)",
  band: "var(--granite)",
  text: "var(--bone)",
  muted: "var(--cinder)",
} as const;

export function defaultMargin(top = 8, right = 8, bottom = 24, left = 32) {
  return { top, right, bottom, left };
}
