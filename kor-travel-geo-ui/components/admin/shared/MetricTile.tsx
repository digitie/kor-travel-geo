import { Skeleton } from "@/components/ui/skeleton";

/**
 * 숫자 지표 타일 (.metric 마크업 유지 — strong 값 + span 라벨).
 * 로딩 중에는 0 대신 Skeleton을 보여 실측 0과 구분한다.
 */
export function MetricTile({
  label,
  value,
  loading = false,
  hint
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  loading?: boolean;
  hint?: React.ReactNode;
}) {
  return (
    <div className="metric">
      {loading ? <Skeleton className="h-9 w-20" /> : <strong>{value}</strong>}
      <span>{label}</span>
      {hint ? <small className="text-xs text-muted-foreground">{hint}</small> : null}
    </div>
  );
}
