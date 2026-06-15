"use client";

import { useQuery } from "@tanstack/react-query";
import { Panel } from "@/components/ui/Panel";
import { RetentionWarning } from "@/components/admin/source-files/RetentionWarning";
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
        <p className="form-note">용량 정보를 불러오는 중…</p>
      ) : (
        <>
        <RetentionWarning retention={capacity.retention} />
        <dl className="criteria-grid">
          <div>
            <dt>객체 수</dt>
            <dd>{capacity.total_object_count.toLocaleString()}</dd>
          </div>
          <div>
            <dt>전체 용량</dt>
            <dd>{formatBytes(capacity.total_bytes)}</dd>
          </div>
          <div>
            <dt>최근 30일 증가</dt>
            <dd>{formatBytes(capacity.growth_30d_bytes)}</dd>
          </div>
          <div>
            <dt>quarantine</dt>
            <dd>{formatBytes(capacity.quarantined_bytes)}</dd>
          </div>
          <div>
            <dt>soft-delete</dt>
            <dd>{formatBytes(capacity.soft_deleted_bytes)}</dd>
          </div>
          <div>
            <dt>미등록</dt>
            <dd>{formatBytes(capacity.unregistered_bytes)}</dd>
          </div>
          <div>
            <dt>한도 초과</dt>
            <dd>{capacity.over_threshold ? "예" : "아니오"}</dd>
          </div>
          <div>
            <dt>미해결 이슈</dt>
            <dd>{openIssues.total.toLocaleString()}</dd>
          </div>
          <div>
            <dt>오류(error) 이슈</dt>
            <dd>{openIssues.error.toLocaleString()}</dd>
          </div>
        </dl>
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
