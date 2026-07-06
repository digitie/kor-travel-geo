import { Badge } from "@/components/ui/badge";
import { severityClass } from "@/lib/consistency";

/**
 * 상태 문자열 배지 — Badge 위에 severity 색 매핑을 얹은 래퍼.
 * `status <tone>` 클래스는 e2e가 span.status로 선택하는 관성 훅으로 유지한다.
 */
export function StatusBadge({
  value,
  tone
}: {
  value: string;
  /** Override the severity-derived colour (e.g. serving-usage badges). */
  tone?: "ok" | "warn" | "error";
}) {
  const resolved = tone ?? severityClass(value);
  return (
    <Badge tone={resolved} className={`status ${resolved}`}>
      {value}
    </Badge>
  );
}
