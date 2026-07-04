import type { ReactNode } from "react";
import { useToastStore } from "@/state/toast";

export function ToastHost() {
  const message = useToastStore((s) => s.message);
  const undo = useToastStore((s) => s.undo);
  const dismiss = useToastStore((s) => s.dismiss);

  if (!message) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3 rounded-card border border-quartz-vein bg-slate px-4 py-3 shadow-stone">
      <span className="text-sm text-bone">{message}</span>
      {undo ? (
        <button
          type="button"
          className="font-mono text-xs text-copper hover:underline"
          onClick={() => {
            undo();
            dismiss();
          }}
        >
          Undo
        </button>
      ) : null}
      <button type="button" className="text-cinder hover:text-bone" onClick={dismiss}>
        ×
      </button>
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  return (
    <>
      {children}
      <ToastHost />
    </>
  );
}
