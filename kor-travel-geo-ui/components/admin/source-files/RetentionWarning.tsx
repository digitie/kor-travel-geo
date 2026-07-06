"use client";

import { AlertTriangle } from "lucide-react";
import { KeyValueGrid } from "@/components/admin/shared/KeyValueGrid";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
    <Alert role="alert" variant="warning">
      <AlertTriangle aria-hidden="true" />
      <AlertTitle>저장소 용량 한도 초과 — 정리 권장</AlertTitle>
      <AlertDescription>
        {retention.guidance ? <p>{retention.guidance}</p> : null}
        <KeyValueGrid
          items={[
            { label: "정리 가능 용량", value: formatBytes(retention.reclaimable_bytes) },
            {
              label: "정리 대상 객체",
              value: `${retention.eligible_object_count.toLocaleString()}건`
            }
          ]}
        />
      </AlertDescription>
    </Alert>
  );
}
