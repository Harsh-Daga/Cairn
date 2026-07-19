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
export const MAX_VISIBLE_SERIES = 7;

export function seriesColor(index: number): string {
  const i = index % CHART_SERIES.length;
  return CHART_SERIES[i] as string;
}

export const chartColors = {
  axis: "var(--ash)",
  grid: "var(--quartz-vein)",
  fill: "var(--copper)",
  fillWarn: "var(--cinnabar)",
  fillGood: "var(--malachite)",
  stroke: "var(--copper)",
  band: "var(--granite)",
  text: "var(--bone)",
  muted: "var(--ash)",
} as const;

export function defaultMargin(top = 8, right = 8, bottom = 24, left = 32) {
  return { top, right, bottom, left };
}

export function aggregateOtherSeries(
  data: ReadonlyArray<Record<string, number | string>>,
  keys: ReadonlyArray<string>,
  maximum = MAX_VISIBLE_SERIES,
): { data: Array<Record<string, number | string>>; keys: string[] } {
  if (keys.length <= maximum) return { data: data.map((row) => ({ ...row })), keys: [...keys] };
  const retained = keys.slice(0, Math.max(1, maximum - 1));
  const remainder = keys.slice(retained.length);
  return {
    keys: [...retained, "other"],
    data: data.map((row) => ({
      ...row,
      other: remainder.reduce((sum, key) => sum + Number(row[key] ?? 0), 0),
    })),
  };
}
