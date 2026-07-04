import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useUiStore } from "@/state/ui";
import { fetchActions, runAction } from "@/lib/api";

export function CommandPalette() {
  const open = useUiStore((s) => s.paletteOpen);
  const setOpen = useUiStore((s) => s.setPaletteOpen);
  const [query, setQuery] = useState("");

  const { data } = useQuery({
    queryKey: ["actions"],
    queryFn: fetchActions,
    enabled: open,
  });

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

  const actions = (data?.actions ?? []).filter(
    (a) =>
      !query ||
      a.name.includes(query.toLowerCase()) ||
      a.title.toLowerCase().includes(query.toLowerCase()),
  );

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
          placeholder="Search actions…"
          value={query}
          className="w-full rounded-sm border border-quartz-vein bg-shale px-3 py-2 font-ui text-sm text-bone placeholder:text-ash focus:border-copper focus:outline-none"
          autoFocus
          onChange={(e) => setQuery(e.target.value)}
        />
        <ul className="mt-3 max-h-64 overflow-auto">
          {actions.map((action) => (
            <li key={action.name}>
              <button
                type="button"
                className="flex w-full items-center justify-between rounded-sm px-2 py-2 text-left text-sm text-bone hover:bg-shale"
                onClick={() => {
                  runAction(action.name).catch(console.error);
                  setOpen(false);
                }}
              >
                <span>{action.title}</span>
                <span className="font-mono text-[10px] text-cinder">{action.name}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
