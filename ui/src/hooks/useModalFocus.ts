import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE =
  "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), " +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useModalFocus(
  open: boolean,
  containerRef: RefObject<HTMLElement | null>,
  onClose: () => void,
  initialFocusRef?: RefObject<HTMLElement | null>,
  returnFocusSelector?: string,
): void {
  const restoreTarget = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const container = containerRef.current;
    const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!container?.contains(active)) restoreTarget.current = active;
    const initial =
      initialFocusRef?.current ?? container?.querySelector<HTMLElement>(FOCUSABLE) ?? container;
    initial?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !container) return;
      const focusable = [...container.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (element) => element.offsetParent !== null,
      );
      if (focusable.length === 0) {
        event.preventDefault();
        container.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      window.setTimeout(() => {
        if (!container?.isConnected) {
          const target = restoreTarget.current?.isConnected
            ? restoreTarget.current
            : returnFocusSelector
              ? document.querySelector<HTMLElement>(returnFocusSelector)
              : null;
          target?.focus();
          restoreTarget.current = null;
        }
      }, 0);
    };
  }, [containerRef, initialFocusRef, onClose, open, returnFocusSelector]);
}
