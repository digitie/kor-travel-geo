"use client";

import { Toast as ToastPrimitive } from "radix-ui";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { useToastStore, type ToastTone } from "@/lib/toast";

const toneIcon: Record<ToastTone, typeof Info> = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info
};

const toneClass: Record<ToastTone, string> = {
  success: "text-[var(--ok)]",
  error: "text-[var(--danger)]",
  info: "text-[var(--info)]"
};

/** Global toast outlet — mounted once in app/providers.tsx. */
export function Toaster() {
  const toasts = useToastStore((state) => state.toasts);
  const dismiss = useToastStore((state) => state.dismiss);

  return (
    <ToastPrimitive.Provider swipeDirection="right" label="알림">
      {toasts.map((item) => {
        const Icon = toneIcon[item.tone];
        return (
          <ToastPrimitive.Root
            key={item.id}
            duration={item.duration}
            onOpenChange={(open) => {
              if (!open) dismiss(item.id);
            }}
            className="grid grid-cols-[auto_1fr_auto] items-start gap-x-2.5 rounded-lg bg-card p-3.5 text-sm shadow-[var(--shadow-modal)] ring-1 ring-foreground/10"
          >
            <Icon aria-hidden="true" className={cn("mt-0.5 size-4", toneClass[item.tone])} />
            <div className="grid gap-0.5">
              <ToastPrimitive.Title className="font-semibold text-foreground">
                {item.title}
              </ToastPrimitive.Title>
              {item.description ? (
                <ToastPrimitive.Description className="break-all text-muted-foreground">
                  {item.description}
                </ToastPrimitive.Description>
              ) : null}
            </div>
            <ToastPrimitive.Close
              aria-label="알림 닫기"
              className="inline-flex size-6 items-center justify-center rounded-md text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <X className="size-3.5" />
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        );
      })}
      <ToastPrimitive.Viewport className="fixed right-4 bottom-4 z-[100] flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2 outline-none" />
    </ToastPrimitive.Provider>
  );
}
