export const RECAP_VIEWED_KEY = "cairn.recap.lastViewed";

export function recapPeriodKey(value: string | number): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  const dayFromMonday = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - dayFromMonday);
  date.setUTCHours(0, 0, 0, 0);
  return date.toISOString().slice(0, 10);
}

export function shouldShowRecap(lastViewed: string | null, now = Date.now()): boolean {
  if (!lastViewed) return true;
  const viewedPeriod = /^\d{4}-\d{2}-\d{2}$/.test(lastViewed)
    ? lastViewed
    : recapPeriodKey(lastViewed);
  return !viewedPeriod || viewedPeriod !== recapPeriodKey(now);
}
