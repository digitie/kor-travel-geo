"use client";

import { useQuery } from "@tanstack/react-query";
import { KeyValueGrid } from "@/components/admin/shared/KeyValueGrid";
import { RetentionWarning } from "@/components/admin/source-files/RetentionWarning";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/skeleton";
import { requestJson } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import {
  sourceFilesPaths,
  type SourceCapacityUsage,
  type SourceReconcileItem,
  type SourceReconcileItemPage,
  type SourceReconcileRun
} from "@/lib/source-files";

const EMPTY_RUNS: SourceReconcileRun[] = [];

/**
 * T-211 용량/이슈 요약 카드 (doc line ~2107).
 *
 * Reuses ``GET /admin/source-files/capacity`` (T-204) for category object
 * count/bytes, the 30-day growth, and the quarantined/soft_deleted/unregistered
 * byte breakdown, and the latest reconcile run's items for the open-issue count.
 * The detailed per-category capacity table stays in the RustFS 정합성 tab
 * (T-209); this is the concise overview surfaced on the list tab.
 */
export function CapacitySummaryCard() {
  const { data: capacity } = useQuery({
    queryKey: ["source-capacity"],
    queryFn: () => requestJson<SourceCapacityUsage>(sourceFilesPaths.capacity())
  });

  const { data: runs = EMPTY_RUNS } = useQuery({
    queryKey: ["reconcile-runs"],
    queryFn: () => requestJson<SourceReconcileRun[]>(sourceFilesPaths.reconcileList())
  });
  const latestRunId = runs[0]?.source_storage_reconcile_run_id ?? null;

  const { data: itemPage } = useQuery({
    queryKey: ["reconcile-items", latestRunId],
    queryFn: () =>
      requestJson<SourceReconcileItemPage>(sourceFilesPaths.reconcileItems(latestRunId!)),
    enabled: latestRunId !== null
  });
  const openIssues = countOpenIssues(itemPage?.items ?? []);

  return (
    <Panel title="용량 / 이슈 요약">
      {!capacity ? (
        <div className="grid gap-2">
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-4/5" />
          <Skeleton className="h-5 w-2/3" />
        </div>
      ) : (
        <>
          <RetentionWarning retention={capacity.retention} />
          <KeyValueGrid
            items={[
              { label: "객체 수", value: capacity.total_object_count.toLocaleString() },
              { label: "전체 용량", value: formatBytes(capacity.total_bytes) },
              { label: "최근 30일 증가", value: formatBytes(capacity.growth_30d_bytes) },
              { label: "quarantine", value: formatBytes(capacity.quarantined_bytes) },
              { label: "soft-delete", value: formatBytes(capacity.soft_deleted_bytes) },
              { label: "미등록", value: formatBytes(capacity.unregistered_bytes) },
              { label: "한도 초과", value: capacity.over_threshold ? "예" : "아니오" },
              { label: "미해결 이슈", value: openIssues.total.toLocaleString() },
              { label: "오류(error) 이슈", value: openIssues.error.toLocaleString() }
            ]}
          />
        </>
      )}
    </Panel>
  );
}

function countOpenIssues(items: SourceReconcileItem[]): { total: number; error: number } {
  let total = 0;
  let error = 0;
  for (const item of items) {
    if (item.state !== "open") continue;
    total += 1;
    if (item.severity === "error") error += 1;
  }
  return { total, error };
}
