import { create } from "zustand";

export type ToastKind = "default" | "good" | "error";

interface ToastState {
  message: string | null;
  kind: ToastKind;
  undo?: () => void;
  show: (message: string, undo?: () => void, kind?: ToastKind) => void;
  dismiss: () => void;
}

export const useToastStore = create<ToastState>((set) => ({
  message: null,
  kind: "default",
  show: (message, undo, kind = "default") => set({ message, undo, kind }),
  dismiss: () => set({ message: null, undo: undefined, kind: "default" }),
}));
