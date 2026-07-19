import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type RefObject,
  type ReactNode,
} from "react";
import { useModalFocus } from "@/hooks/useModalFocus";

export function Tooltip({ content, children }: { content: ReactNode; children: ReactNode }) {
  const id = useId();
  return (
    <span className="group relative inline-flex" tabIndex={0} aria-describedby={id}>
      {children}
      <span
        id={id}
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 hidden w-max max-w-64 -translate-x-1/2 rounded-sm border border-quartz-vein bg-overlay px-2 py-1 text-xs text-bone shadow-stone group-hover:block group-focus:block group-focus-within:block"
      >
        {content}
      </span>
    </span>
  );
}

export function Popover({
  label,
  trigger,
  children,
}: {
  label: string;
  trigger: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return (
    <span ref={rootRef} className="relative inline-flex">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        className="inline-flex min-h-9 items-center"
        onClick={() => setOpen((value) => !value)}
      >
        {trigger}
      </button>
      {open ? (
        <div
          role="dialog"
          aria-label={label}
          className="absolute right-0 top-full z-50 mt-2 w-72 rounded-sm border border-quartz-vein bg-overlay p-3 text-sm text-bone shadow-stone"
        >
          {children}
        </div>
      ) : null}
    </span>
  );
}

export function Dialog({
  open,
  title,
  onClose,
  children,
  footer,
  initialFocusRef,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  initialFocusRef?: RefObject<HTMLElement | null>;
}) {
  const id = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const close = useCallback(onClose, [onClose]);
  useModalFocus(open, dialogRef, close, initialFocusRef);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-anthracite/70 p-4"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={id}
        className="card max-h-[min(90vh,720px)] w-full max-w-lg overflow-y-auto p-5"
      >
        <header className="flex items-center justify-between gap-4">
          <h2 id={id} className="font-display text-lg text-bone">
            {title}
          </h2>
          <button
            type="button"
            aria-label={`Close ${title}`}
            className="min-h-9 min-w-9 rounded-sm text-cinder hover:text-bone"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="mt-4">{children}</div>
        {footer ? <footer className="mt-5 flex justify-end gap-2">{footer}</footer> : null}
      </div>
    </div>
  );
}

export function SidePanel({
  open,
  title,
  onClose,
  children,
  initialWidth = 480,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  initialWidth?: number;
}) {
  const [width, setWidth] = useState(initialWidth);
  const id = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const close = useCallback(onClose, [onClose]);
  useModalFocus(open, panelRef, close);
  if (!open) return null;
  const resize = (delta: number) =>
    setWidth((value) => Math.min(760, Math.max(320, value + delta)));
  return (
    <div className="fixed inset-0 z-50 bg-anthracite/60" onPointerDown={onClose}>
      <aside
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={id}
        className="absolute inset-y-0 right-0 max-w-full overflow-y-auto border-l border-quartz-vein bg-overlay p-5 shadow-stone"
        style={{ width }}
        onPointerDown={(event) => event.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-3">
          <h2 id={id} className="font-display text-lg text-bone">
            {title}
          </h2>
          <button type="button" className="min-h-9 px-2 text-cinder" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="mt-3 flex gap-2" aria-label="Panel width controls">
          <button
            type="button"
            className="min-h-9 rounded-sm border border-quartz-vein px-3 text-xs"
            onClick={() => resize(-80)}
            aria-label="Make panel narrower"
          >
            Narrower
          </button>
          <button
            type="button"
            className="min-h-9 rounded-sm border border-quartz-vein px-3 text-xs"
            onClick={() => resize(80)}
            aria-label="Make panel wider"
          >
            Wider
          </button>
        </div>
        <div className="mt-4">{children}</div>
      </aside>
    </div>
  );
}
