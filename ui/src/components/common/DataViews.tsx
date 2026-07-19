import { Link } from "react-router-dom";
import { EmptyState, InlineError } from "@/components/ui";

interface ErrorCardProps {
  message?: string;
}

export function ErrorCard({ message }: ErrorCardProps) {
  return <InlineError message={message ?? "Couldn't reach the local server — is cairn running?"} />;
}

interface EmptyCardProps {
  title: string;
  detail: string;
  action?: React.ReactNode;
}

export function EmptyCard({ title, detail, action }: EmptyCardProps) {
  return <EmptyState title={title} detail={detail} action={action} />;
}

interface HorizontalBarsProps {
  items: { label: string; value: number; to?: string }[];
  max?: number;
}

export function HorizontalBars({ items, max }: HorizontalBarsProps) {
  const peak = max ?? Math.max(...items.map((i) => i.value), 1);
  return (
    <ul className="space-y-2">
      {items.map((item) => {
        const pct = Math.round((item.value / peak) * 100);
        const row = (
          <>
            <div className="mb-1 flex justify-between font-mono text-xs text-cinder">
              <span className="text-bone">{item.label}</span>
              <span>{item.value.toLocaleString()}</span>
            </div>
            <div className="h-2 rounded-sm bg-granite">
              <div className="h-2 rounded-sm bg-copper" style={{ width: `${pct}%` }} />
            </div>
          </>
        );
        return (
          <li key={item.label}>
            {item.to ? (
              <Link to={item.to} className="block hover:opacity-90">
                {row}
              </Link>
            ) : (
              row
            )}
          </li>
        );
      })}
    </ul>
  );
}
