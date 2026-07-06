import { cn } from "@/lib/utils";

/**
 * admin/debug 공용 섹션 카드. `<section className="panel">` + `.panel-header h2`
 * 구조는 e2e가 컨테이너 셀렉터로 쓰는 계약이라 유지한다.
 * h2 접근명은 title 문자열만으로 구성된다 — 배지는 badges 슬롯으로 heading 밖에 둔다.
 */
export function Panel({
  title,
  badges,
  description,
  children,
  actions,
  className
}: {
  title: string;
  /** 제목 옆 배지 (heading 접근명에 포함되지 않음). */
  badges?: React.ReactNode;
  /** 제목 아래 한 줄 부연 (짧게 — 상세는 HelpTip으로). */
  description?: React.ReactNode;
  children: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("panel", className)}>
      <div className="panel-header">
        <div className="grid min-w-0 gap-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2>{title}</h2>
            {badges}
          </div>
          {description ? (
            <p className="m-0 text-xs text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            {actions}
          </div>
        ) : null}
      </div>
      <div className="panel-body">{children}</div>
    </section>
  );
}
