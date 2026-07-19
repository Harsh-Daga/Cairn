import type { ReactNode } from "react";

export function EmptyState({
  title,
  detail,
  action,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
}) {
  return (
    <section className="card empty-state">
      <h2>{title}</h2>
      <p className="mt-2 text-sm">{detail}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </section>
  );
}

export function Skeleton({
  label = "Loading",
  className = "h-32",
}: {
  label?: string;
  className?: string;
}) {
  return (
    <div className={`skeleton rounded-sm ${className}`} role="status" aria-label={label}>
      <span className="sr-only">{label}…</span>
    </div>
  );
}

export function InlineError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-sm border border-critical/50 bg-critical/10 p-3 text-sm">
      <p className="text-critical">{message}</p>
      {onRetry ? (
        <button
          type="button"
          className="mt-2 min-h-9 rounded-sm border border-critical/60 px-3 text-xs text-critical"
          onClick={onRetry}
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}
