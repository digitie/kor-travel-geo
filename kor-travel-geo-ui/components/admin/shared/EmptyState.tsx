import { cn } from "@/lib/utils";

/** 빈 목록/결과 없음 표준 문구 래퍼 (문구 자체는 호출부 계약 그대로). */
export function EmptyState({
  className,
  children
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <p className={cn("m-0 py-2 text-sm text-muted-foreground", className)}>{children}</p>
  );
}
