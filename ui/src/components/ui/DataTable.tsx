import { useMemo, useRef, type ReactNode } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

export interface DataTableColumn<Row> {
  key: string;
  header: string;
  cell: (row: Row) => ReactNode;
  numeric?: boolean;
  sortable?: boolean;
  className?: string;
}

interface DataTableProps<Row> {
  label: string;
  columns: ReadonlyArray<DataTableColumn<Row>>;
  rows: ReadonlyArray<Row>;
  rowKey: (row: Row) => string;
  sort?: { key: string; direction: "ascending" | "descending" };
  onSort?: (key: string) => void;
  page?: number;
  pageCount?: number;
  totalRows?: number;
  onPageChange?: (page: number) => void;
  selectedKey?: string | null;
  onSelect?: (row: Row) => void;
  empty?: ReactNode;
  virtualizeAbove?: number;
}

export function DataTable<Row>({
  label,
  columns,
  rows,
  rowKey,
  sort,
  onSort,
  page = 1,
  pageCount = 1,
  totalRows = rows.length,
  onPageChange,
  selectedKey,
  onSelect,
  empty,
  virtualizeAbove = 100,
}: DataTableProps<Row>) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtual = rows.length > virtualizeAbove;
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 44,
    overscan: 12,
    enabled: virtual,
    initialRect: { width: 1024, height: 480 },
  });
  const visible = virtualizer.getVirtualItems();
  const initialVirtualCount = Math.min(rows.length, 24);
  const rowIndexes = useMemo(
    () =>
      virtual
        ? visible.length > 0
          ? visible.map((item) => item.index)
          : Array.from({ length: initialVirtualCount }, (_value, index) => index)
        : rows.map((_row, index) => index),
    [initialVirtualCount, rows, virtual, visible],
  );
  const topSpacer = virtual && visible[0] ? visible[0].start : 0;
  const last = visible.at(-1);
  const bottomSpacer = virtual
    ? last
      ? Math.max(0, virtualizer.getTotalSize() - last.end)
      : Math.max(0, rows.length - initialVirtualCount) * 44
    : 0;

  const moveFocus = (index: number, direction: -1 | 1) => {
    const nextIndex = Math.max(0, Math.min(rows.length - 1, index + direction));
    if (virtual) virtualizer.scrollToIndex(nextIndex, { align: "auto" });
    window.requestAnimationFrame(() => {
      scrollRef.current?.querySelector<HTMLElement>(`[data-table-index="${nextIndex}"]`)?.focus();
    });
    const next = rows[nextIndex];
    if (next) onSelect?.(next);
  };

  return (
    <section className="card overflow-hidden">
      <div
        ref={scrollRef}
        tabIndex={0}
        className="max-h-[min(70vh,720px)] overflow-auto"
        aria-label={`${label} scroll region`}
      >
        <table className="w-full text-left text-sm" aria-label={label}>
          <caption className="sr-only">
            {totalRows} row{totalRows === 1 ? "" : "s"}, page {page} of {pageCount}
          </caption>
          <thead className="sticky top-0 z-10 bg-slate text-xs text-cinder">
            <tr>
              {columns.map((column) => {
                const active = sort?.key === column.key;
                return (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={active ? sort.direction : column.sortable ? "none" : undefined}
                    className={`px-4 py-3 ${column.numeric ? "text-right" : ""} ${column.className ?? ""}`}
                  >
                    {column.sortable && onSort ? (
                      <button
                        type="button"
                        className="min-h-9 font-mono uppercase tracking-wide hover:text-bone"
                        onClick={() => onSort(column.key)}
                      >
                        {column.header}
                        {active ? (
                          <span aria-hidden="true">
                            {sort.direction === "ascending" ? " ↑" : " ↓"}
                          </span>
                        ) : null}
                      </button>
                    ) : (
                      column.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {topSpacer > 0 ? (
              <tr aria-hidden="true">
                <td colSpan={columns.length} style={{ height: topSpacer, padding: 0 }} />
              </tr>
            ) : null}
            {rowIndexes.map((index) => {
              const row = rows[index];
              if (!row) return null;
              const key = rowKey(row);
              const selected = selectedKey === key;
              return (
                <tr
                  key={key}
                  data-table-index={index}
                  tabIndex={selected || (selectedKey == null && index === 0) ? 0 : -1}
                  aria-selected={selected}
                  className={`border-t border-quartz-vein/50 ${selected ? "bg-copper/10" : "hover:bg-granite/20"}`}
                  onClick={() => onSelect?.(row)}
                  onFocus={() => onSelect?.(row)}
                  onKeyDown={(event) => {
                    if (event.key === "j" || event.key === "ArrowDown") {
                      event.preventDefault();
                      moveFocus(index, 1);
                    } else if (event.key === "k" || event.key === "ArrowUp") {
                      event.preventDefault();
                      moveFocus(index, -1);
                    } else if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect?.(row);
                    }
                  }}
                >
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={`px-4 py-3 ${column.numeric ? "text-right font-mono" : ""} ${column.className ?? ""}`}
                    >
                      {column.cell(row)}
                    </td>
                  ))}
                </tr>
              );
            })}
            {bottomSpacer > 0 ? (
              <tr aria-hidden="true">
                <td colSpan={columns.length} style={{ height: bottomSpacer, padding: 0 }} />
              </tr>
            ) : null}
          </tbody>
        </table>
        {rows.length === 0 ? (
          <div className="p-6 text-center text-sm text-cinder">{empty ?? "No rows"}</div>
        ) : null}
      </div>
      {pageCount > 1 && onPageChange ? (
        <nav
          aria-label={`${label} pages`}
          className="flex items-center justify-between border-t border-quartz-vein px-4 py-3"
        >
          <button
            type="button"
            disabled={page <= 1}
            className="min-h-9 rounded-sm border border-quartz-vein px-3 text-xs disabled:opacity-50"
            onClick={() => onPageChange(page - 1)}
          >
            Previous
          </button>
          <span className="font-mono text-xs text-cinder" aria-live="polite">
            Page {page} of {pageCount}
          </span>
          <button
            type="button"
            disabled={page >= pageCount}
            className="min-h-9 rounded-sm border border-quartz-vein px-3 text-xs disabled:opacity-50"
            onClick={() => onPageChange(page + 1)}
          >
            Next
          </button>
        </nav>
      ) : null}
    </section>
  );
}
