import type { ReactNode } from "react";
import { useToastStore } from "@/state/toast";

export function ToastHost() {
  const message = useToastStore((s) => s.message);
  const kind = useToastStore((s) => s.kind);
  const undo = useToastStore((s) => s.undo);
  const dismiss = useToastStore((s) => s.dismiss);

  if (!message) return null;

  const kindClass = kind === "good" ? "good" : kind === "error" ? "error" : "";

  return (
    <div className="toast-host" role="status" aria-live="polite">
      <div className={`toast-item ${kindClass}`.trim()}>
        <div className="flex items-center gap-3">
          <span className="flex-1">{message}</span>
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
      </div>
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
