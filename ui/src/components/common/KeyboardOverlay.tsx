import { useUiStore } from "@/state/ui";

const SHORTCUTS = [
  { keys: "⌘K", description: "Open command palette" },
  { keys: "?", description: "Show keyboard shortcuts" },
  { keys: "[ / ]", description: "Cycle global time range" },
  { keys: "g then s", description: "Go to Sessions" },
  { keys: "j / k", description: "Move selection on Sessions" },
  { keys: "Enter", description: "Open selected session" },
  { keys: "Esc", description: "Close overlay / reset zoom" },
] as const;

export function KeyboardOverlay() {
  const open = useUiStore((s) => s.shortcutsOpen);
  const setOpen = useUiStore((s) => s.setShortcutsOpen);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-anthracite/70 p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      onClick={() => setOpen(false)}
    >
      <div
        className="card w-full max-w-md p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="font-display text-lg text-bone">Keyboard shortcuts</h2>
          <button
            type="button"
            className="font-mono text-xs text-cinder hover:text-bone"
            onClick={() => setOpen(false)}
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
