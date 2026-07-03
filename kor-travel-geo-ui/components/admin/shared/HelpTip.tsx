"use client";

import { Info } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/**
 * 필드/제목 옆 정보 아이콘 버튼. 상세 설명은 화면에 상시 노출하는 대신 여기로
 * 옮긴다. 클릭/키보드로 열리는 Popover라 터치·스크린리더 모두 접근 가능하다.
 */
export function HelpTip({
  label = "도움말",
  className,
  children
}: {
  /** 아이콘 버튼의 접근명 (예: "복원 대상 DB 이름 도움말"). */
  label?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={label}
          className={cn(
            "inline-flex size-5 shrink-0 items-center justify-center rounded-full align-middle text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50",
            className
          )}
        >
          <Info className="size-3.5" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="text-xs leading-relaxed">{children}</PopoverContent>
    </Popover>
  );
}
