"use client";

import { AlertTriangle } from "lucide-react";
import { formatBytes } from "@/lib/format";
import type { SourceRetentionRecommendation } from "@/lib/source-files";

/**
 * T-212 (ADR-052) "UI 경고" deliverable — surfaces the backend's advisory
 * retention recommendation (`SourceCapacityUsage.retention`) as an emphasized
 * warning when storage is over the capacity threshold. The policy never
 * auto-deletes; this only guides the operator toward the manual "정리 대상"
 * bulk hard-delete. Renders nothing unless `over_threshold` is set.
 */
export function RetentionWarning({
  retention
}: {
  retention?: SourceRetentionRecommendation | null;
}) {
  if (!retention?.over_threshold) {
    return null;
  }
  return (
    <div className="retention-alert" role="alert">
      <div className="retention-alert-head">
        <AlertTriangle size={16} />
        <strong>저장소 용량 한도 초과 — 정리 권장</strong>
      </div>
      {retention.guidance ? <p>{retention.guidance}</p> : null}
      <dl className="criteria-grid">
        <div>
          <dt>정리 가능 용량</dt>
          <dd>{formatBytes(retention.reclaimable_bytes)}</dd>
        </div>
        <div>
          <dt>정리 대상 객체</dt>
          <dd>{retention.eligible_object_count.toLocaleString()}건</dd>
        </div>
      </dl>
    </div>
  );
}
