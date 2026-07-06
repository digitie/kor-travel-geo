"use client";

import { create } from "zustand";

export type ToastTone = "success" | "error" | "info";

export interface ToastItem {
  id: number;
  tone: ToastTone;
  title: string;
  description?: string;
  /** ms before auto-dismiss. Errors stay longer by default. */
  duration: number;
}

interface ToastStore {
  toasts: ToastItem[];
  push: (toast: Omit<ToastItem, "id" | "duration"> & { duration?: number }) => void;
  dismiss: (id: number) => void;
}

let nextToastId = 1;

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  push: ({ duration, ...toast }) =>
    set((state) => ({
      toasts: [
        ...state.toasts.slice(-4),
        {
          ...toast,
          id: nextToastId++,
          duration: duration ?? (toast.tone === "error" ? 8000 : 4000)
        }
      ]
    })),
  dismiss: (id) =>
    set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) }))
}));

function push(tone: ToastTone, title: string, description?: string) {
  useToastStore.getState().push({ tone, title, description });
}

/** Imperative toast API for mutation feedback (rendered by components/ui/toaster.tsx). */
export const toast = {
  success: (title: string, description?: string) => push("success", title, description),
  error: (title: string, description?: string) => push("error", title, description),
  info: (title: string, description?: string) => push("info", title, description)
};
