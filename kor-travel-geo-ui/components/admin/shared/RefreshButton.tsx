"use client";

import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** 새로고침 버튼 표준 (aria-label 내장, busy 시 스피너+비활성). */
export function RefreshButton({
  onClick,
  busy = false,
  iconOnly = false,
  label = "새로고침",
  className
}: {
  onClick: () => void;
  busy?: boolean;
  iconOnly?: boolean;
  label?: string;
  className?: string;
}) {
  return (
    <Button
      type="button"
      variant="outline"
      size={iconOnly ? "icon-sm" : "sm"}
      aria-label={label}
      aria-busy={busy || undefined}
      disabled={busy}
      onClick={onClick}
      className={className}
    >
      <RefreshCw aria-hidden="true" className={cn(busy && "animate-spin")} />
      {iconOnly ? null : label}
    </Button>
  );
}
