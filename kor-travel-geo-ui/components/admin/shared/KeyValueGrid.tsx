import { HelpTip } from "@/components/admin/shared/HelpTip";
import { cn } from "@/lib/utils";

export interface KeyValueItem {
  label: React.ReactNode;
  value: React.ReactNode;
  /** 라벨 옆 도움말 (API 필드명, 계산 방식 등 상세 설명). */
  help?: React.ReactNode;
  /** help 아이콘의 접근명. */
  helpLabel?: string;
}

/**
 * dt/dd 키-값 요약 그리드 공용 컴포넌트 (기존 .criteria-grid 마크업/클래스 유지).
 * admin 표면 9곳+에서 반복되던 <dl className="criteria-grid"> 패턴을 대체한다.
 */
export function KeyValueGrid({
  items,
  className
}: {
  items: KeyValueItem[];
  className?: string;
}) {
  return (
    <dl className={cn("criteria-grid", className)}>
      {items.map((item, index) => (
        <div key={typeof item.label === "string" ? item.label : index}>
          <dt className="flex items-center gap-1">
            {item.label}
            {item.help ? (
              <HelpTip label={item.helpLabel ?? "도움말"}>{item.help}</HelpTip>
            ) : null}
          </dt>
          <dd className="break-all">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
