"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger
} from "@/components/ui/collapsible";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { cn } from "@/lib/utils";

/**
 * 원본 JSON을 접이식으로 보여준다. 요약 UI가 주 정보를 전달하고,
 * raw JSON은 필요할 때만 펼쳐 본다. (mock spec이 pre 내용을 어서션하는
 * '최근 결과' 계열은 defaultOpen을 켠 채 사용한다.)
 */
export function JsonDetails({
  value,
  summary = "원본 JSON",
  defaultOpen = false,
  className
}: {
  value: unknown;
  summary?: string;
  defaultOpen?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className={className}>
      <CollapsibleTrigger className="inline-flex min-h-9 items-center gap-1 rounded-md px-1.5 text-xs font-semibold text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
        <ChevronDown
          aria-hidden="true"
          className={cn(
            "size-3.5 transition-transform duration-[var(--duration-fast)]",
            !open && "-rotate-90"
          )}
        />
        {summary}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <JsonBlock value={value} />
      </CollapsibleContent>
    </Collapsible>
  );
}
