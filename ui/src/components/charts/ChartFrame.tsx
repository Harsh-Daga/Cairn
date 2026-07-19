import { useId, type ReactNode } from "react";

export interface ChartTableColumn<Row> {
  key: string;
  label: string;
  value: (row: Row) => ReactNode;
  numeric?: boolean;
}

export function ChartFrame<Row>({
  title,
  subtitle,
  summary,
  rows = [],
  columns = [],
  children,
  action,
}: {
  title: string;
  subtitle?: string;
  summary: string;
  rows?: ReadonlyArray<Row>;
  columns?: ReadonlyArray<ChartTableColumn<Row>>;
  children: ReactNode;
  action?: ReactNode;
}) {
  const titleId = useId();
  const summaryId = useId();
  return (
    <figure className="card overflow-hidden" aria-labelledby={titleId} aria-describedby={summaryId}>
      <header className="flex items-start justify-between gap-4 border-b border-quartz-vein/80 px-5 py-4">
        <div>
          <h2 id={titleId} className="font-display text-[15px] font-semibold text-bone">
            {title}
          </h2>
          {subtitle ? <p className="mt-1 text-xs text-cinder">{subtitle}</p> : null}
        </div>
        {action}
      </header>
      <p id={summaryId} className="px-5 pt-4 text-sm text-cinder">
        {summary}
      </p>
      <div className="chart-surface p-5">{children}</div>
      {rows.length > 0 && columns.length > 0 ? (
        <details className="border-t border-quartz-vein px-5 py-3">
          <summary className="min-h-9 cursor-pointer font-mono text-xs text-cinder">
            View chart data
          </summary>
          <div className="mt-3 overflow-x-auto" tabIndex={0}>
            <table className="w-full text-left text-xs" aria-label={`${title} data`}>
              <thead>
                <tr>
                  {columns.map((column) => (
                    <th
                      key={column.key}
                      scope="col"
                      className={`border-b border-quartz-vein px-2 py-2 text-cinder ${
                        column.numeric ? "text-right" : ""
                      }`}
                    >
                      {column.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={index} className="border-b border-quartz-vein/50">
                    {columns.map((column) => (
                      <td
                        key={column.key}
                        className={`px-2 py-2 text-bone ${column.numeric ? "text-right font-mono" : ""}`}
                      >
                        {column.value(row)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </figure>
  );
}
