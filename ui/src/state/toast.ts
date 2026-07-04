import { create } from "zustand";

interface ToastState {
  message: string | null;
  undo?: () => void;
  show: (message: string, undo?: () => void) => void;
  dismiss: () => void;
}

export const useToastStore = create<ToastState>((set) => ({
  message: null,
  show: (message, undo) => set({ message, undo }),
  dismiss: () => set({ message: null, undo: undefined }),
}));
