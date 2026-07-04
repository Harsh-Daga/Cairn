import { useEffect } from "react";
import { useUiStore } from "@/state/ui";

export function CommandPalette() {
  const open = useUiStore((s) => s.paletteOpen);
  const setOpen = useUiStore((s) => s.setPaletteOpen);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(!open);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-anthracite/40 pt-[15vh] backdrop-blur-sm"
      role="dialog"
      aria-label="Command palette"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-lg rounded-modal border border-quartz-vein bg-slate p-4 shadow-stone"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          type="text"
          placeholder="Search pages, sessions, actions…"
          className="w-full rounded-sm border border-quartz-vein bg-shale px-3 py-2 font-ui text-sm text-bone placeholder:text-ash focus:border-copper focus:outline-none"
          autoFocus
        />
        <p className="mt-3 font-mono text-[11px] text-cinder">
          Actions from /api/actions manifest will appear here (Phase 7).
        </p>
      </div>
    </div>
  );
}
