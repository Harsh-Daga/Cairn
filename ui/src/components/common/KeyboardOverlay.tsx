import { useCallback, useRef } from "react";
import { useUiStore } from "@/state/ui";
import { useModalFocus } from "@/hooks/useModalFocus";

const SHORTCUTS = [
  { keys: "⌘K", description: "Open command palette" },
  { keys: "?", description: "Show keyboard shortcuts" },
  { keys: "[ / ]", description: "Cycle global time range" },
  { keys: "/", description: "Search pages, sessions, and actions" },
  { keys: "g then o/s/l/c/i", description: "Go to Overview/Sessions/Live/Context/Insights" },
  { keys: "j / k", description: "Move selection on Sessions" },
  { keys: "Enter", description: "Open selected session" },
  { keys: "Esc", description: "Close overlay / reset zoom" },
] as const;

export function KeyboardOverlay() {
  const open = useUiStore((s) => s.shortcutsOpen);
  const setOpen = useUiStore((s) => s.setShortcutsOpen);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setOpen(false), [setOpen]);
  useModalFocus(open, dialogRef, close, closeRef);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-anthracite/70 p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="keyboard-shortcuts-title"
      onClick={() => setOpen(false)}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="card w-full max-w-md p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 id="keyboard-shortcuts-title" className="font-display text-lg text-bone">
            Keyboard shortcuts
          </h2>
          <button
            ref={closeRef}
            type="button"
            className="font-mono text-xs text-cinder hover:text-bone"
            onClick={() => setOpen(false)}
            aria-label="Close keyboard shortcuts"
          >
            Esc
          </button>
        </div>
        <ul className="mt-4 space-y-2">
          {SHORTCUTS.map((item) => (
            <li key={item.keys} className="flex items-center justify-between gap-4">
              <span className="font-mono text-xs text-copper">{item.keys}</span>
              <span className="text-sm text-cinder">{item.description}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
