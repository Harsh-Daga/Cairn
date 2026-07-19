import { useState } from "react";
import { Link } from "react-router-dom";

export function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };
  return (
    <button
      type="button"
      className="min-h-9 rounded-sm border border-quartz-vein px-3 font-mono text-xs text-bone"
      onClick={() => void copy()}
      aria-live="polite"
    >
      {copied ? "Copied" : label}
    </button>
  );
}

export function Breadcrumbs({ items }: { items: Array<{ label: string; to?: string }> }) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex flex-wrap items-center gap-2 font-mono text-xs text-cinder">
        {items.map((item, index) => {
          const current = index === items.length - 1;
          return (
            <li key={`${item.label}-${index}`} className="flex items-center gap-2">
              {index > 0 ? <span aria-hidden="true">/</span> : null}
              {item.to && !current ? (
                <Link className="hover:text-bone" to={item.to}>
                  {item.label}
                </Link>
              ) : (
                <span aria-current={current ? "page" : undefined} className="text-bone">
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
