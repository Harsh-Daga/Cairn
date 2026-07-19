const numberFormatter = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 0,
});

export function formatNumber(n: number): string {
  return numberFormatter.format(n);
}

export function formatDecimal(n: number, digits = 1): string {
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPercent(n: number, digits = 1): string {
  return `${formatDecimal(n, digits)}%`;
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(iso));
}

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${formatDecimal(n / 1_000_000)}M`;
  if (n >= 1_000) return `${formatDecimal(n / 1_000)}K`;
  return String(n);
}

export function formatCost(n: number, digits = 2): string {
  return `$${formatDecimal(n, digits)}`;
}

export function formatBytes(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  if (abs < 1024) return `${formatNumber(n)} B`;
  if (abs < 1024 ** 2) return `${formatDecimal(n / 1024)} KiB`;
  if (abs < 1024 ** 3) return `${formatDecimal(n / 1024 ** 2)} MiB`;
  return `${formatDecimal(n / 1024 ** 3)} GiB`;
}

export function formatDuration(milliseconds: number | null): string {
  if (milliseconds == null) return "—";
  if (milliseconds < 1_000) return `${formatNumber(milliseconds)} ms`;
  const seconds = milliseconds / 1_000;
  if (seconds < 60) return `${formatDecimal(seconds)} s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  return `${minutes}m ${remaining}s`;
}

export function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
