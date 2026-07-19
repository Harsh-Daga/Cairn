import { useId } from "react";
import type { QueryFilterError, QueryFilterToken } from "@/lib/types";
import { FILTER_SPECS } from "@/lib/generated/filter-grammar";

const suggestions = Object.values(FILTER_SPECS);

function removeRawToken(query: string, raw: string): string {
  const index = query.indexOf(raw);
  if (index < 0) return query;
  return `${query.slice(0, index)} ${query.slice(index + raw.length)}`.replace(/\s+/g, " ").trim();
}

export function FilterQuery({
  label,
  value,
  onChange,
  onSubmit,
  tokens = [],
  errors = [],
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit?: (value: string) => void;
  tokens?: QueryFilterToken[];
  errors?: QueryFilterError[];
  placeholder: string;
}) {
  const listId = useId();
  return (
    <div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit?.(value);
        }}
      >
        <label className="font-mono text-[10px] uppercase tracking-wide text-cinder">
          {label}
          <input
            type="search"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            list={listId}
            placeholder={placeholder}
            className="mt-2 block w-full rounded-sm border border-quartz-vein bg-shale px-4 py-3 font-ui text-sm normal-case tracking-normal text-bone placeholder:text-ash focus:border-copper focus:outline-none"
          />
        </label>
        <datalist id={listId}>
          {suggestions.map((spec) => (
            <option key={spec.example} value={spec.example}>
              {"available" in spec && !spec.available ? "Unavailable: " : ""}
              {spec.example}
            </option>
          ))}
        </datalist>
      </form>
      {tokens.length > 0 ? (
        <ul className="mt-2 flex flex-wrap gap-2" aria-label="Active typed filters">
          {tokens.map((token) => (
            <li key={`${token.field}-${token.raw}`}>
              <button
                type="button"
                className="rounded-chip border border-copper/50 px-2 py-1 font-mono text-[10px] text-copper"
                onClick={() => {
                  const next = removeRawToken(value, token.raw);
                  onChange(next);
                  onSubmit?.(next);
                }}
                aria-label={`Remove filter ${token.raw}`}
              >
                {token.raw} ×
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {errors.length > 0 ? (
        <ul className="mt-2 space-y-1 text-xs text-cinnabar" role="alert">
          {errors.map((error) => (
            <li key={`${error.token}-${error.message}`}>
              {error.token ? `${error.token}: ` : ""}
              {error.message}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="mt-2 text-[10px] leading-4 text-ash">
        Quotes and backslash escaping are supported. Filters are combined with AND. Unsupported
        evidence filters return an explicit unavailable state instead of broadening results.
      </p>
    </div>
  );
}
