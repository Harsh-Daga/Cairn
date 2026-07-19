import type { ReactNode } from "react";

export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: ReadonlyArray<{ value: T; label: string; disabled?: boolean }>;
  onChange: (value: T) => void;
}) {
  return (
    <div
      className="inline-flex rounded-sm border border-quartz-vein bg-slate p-1"
      role="group"
      aria-label={label}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          disabled={option.disabled}
          aria-pressed={value === option.value}
          className={`min-h-9 rounded-chip px-3 text-xs disabled:cursor-not-allowed disabled:opacity-50 ${
            value === option.value ? "bg-granite text-bone shadow-stone" : "text-cinder"
          }`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function LabeledField({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block text-sm text-bone">
      {label}
      {hint ? <span className="ml-2 text-xs text-cinder">{hint}</span> : null}
      <span className="mt-1 block">{children}</span>
      {error ? (
        <span className="mt-1 block text-xs text-critical" role="alert">
          {error}
        </span>
      ) : null}
    </label>
  );
}
