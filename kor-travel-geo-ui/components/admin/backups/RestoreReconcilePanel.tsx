"use client";

import { XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import { EmptyState } from "@/components/admin/shared/EmptyState";
import { IssueList } from "@/components/admin/shared/IssueList";
import { JsonDetails } from "@/components/admin/shared/JsonDetails";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { textValue, triState } from "@/components/admin/backups/manifest-utils";
import { reconcileFromManifest } from "@/components/admin/backups/restore-reconcile-utils";
import {
  getErrorMessage,
  type OpsArtifact,
  type RestoreReconcileResult,
  type RestoreRowCountDiff,
  requestJson
} from "@/lib/api";
import { formatTimestamp } from "@/lib/format";

const reconcileColumns: VirtualColumn<RestoreRowCountDiff>[] = [
  { key: "object", header: "object", cell: (d) => d.object },
  { key: "expected", header: "expected", cell: (d) => d.expected ?? "—" },
  { key: "actual", header: "actual", cell: (d) => d.actual },
  {
    key: "match",
    header: "match",
    cell: (d) => (
      <StatusBadge tone={d.match ? "ok" : "error"} value={d.match ? "ok" : "mismatch"} />
    )
  }
];

/**
 * Post-restore reconcile results (T-253): lists recent ``db_restore_log`` artifacts and, for
 * each, surfaces the T-233 row/MV/sppn/pt_source/source_set PASS/FAIL plus warnings. Restore
 * logs that predate T-233 (no row_count_verification) are shown as "reconcile 없음".
 */
export function RestoreReconcilePanel() {
  const [rows, setRows] = useState<OpsArtifact[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const arts = await requestJson<OpsArtifact[]>(
        "/admin/ops/artifacts?artifact_type=db_restore_log&limit=20"
      );
      setRows(arts);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Panel
      title="복원 reconcile 결과"
      actions={<RefreshButton busy={busy} onClick={() => void load()} />}
    >
      {error ? (
        <Alert role="alert" variant="destructive">
          <XCircle aria-hidden="true" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {loading ? (
        <div className="grid gap-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState>복원 기록이 없습니다. [복원] 위저드로 복원을 실행하세요.</EmptyState>
      ) : (
        <div className="reconcile-list">
          {rows.map((artifact) => (
            <RestoreReconcileCard
              artifact={artifact}
              key={artifact.artifact_id}
              reconcile={reconcileFromManifest(artifact.manifest)}
            />
          ))}
        </div>
      )}
    </Panel>
  );
}

function RestoreReconcileCard({
  artifact,
  reconcile
}: {
  artifact: OpsArtifact;
  reconcile: RestoreReconcileResult | null;
}) {
  const target =
    reconcile?.target_database ?? textValue(artifact.manifest?.["target_database"]) ?? "—";
  const mv = triState(reconcile?.mv_nonempty_ok);
  return (
    <div className="reconcile-card">
      <div className="reconcile-head">
        <strong>{artifact.display_name ?? artifact.artifact_id}</strong>
        {reconcile ? (
          <StatusBadge tone={reconcile.ok ? "ok" : "error"} value={reconcile.ok ? "PASS" : "FAIL"} />
        ) : (
          <StatusBadge tone="warn" value="reconcile 없음" />
        )}
      </div>
      <p className="wizard-hint">
        대상 DB: {String(target)} · {formatTimestamp(artifact.created_at)}
      </p>
      {reconcile ? (
        <>
          {reconcile.row_count_diffs && reconcile.row_count_diffs.length > 0 ? (
            <VirtualTable
              as="table"
              caption="행 수 검증"
              columns={reconcileColumns}
              compact
              rowKey={(d) => d.object}
              rows={reconcile.row_count_diffs}
            />
          ) : null}
          <ul className="manifest-kv">
            <li className="flex flex-wrap items-center gap-1">
              MV non-empty: <StatusBadge tone={mv.tone} value={mv.label} /> · mv_target{" "}
              {reconcile.mv_geocode_target_rows ?? "—"} / mv_text{" "}
              {reconcile.mv_geocode_text_search_rows ?? "—"}
            </li>
            <li>sppn: {reconcile.sppn_rows ?? "—"}</li>
          </ul>
          {reconcile.pt_source_distribution ? (
            <JsonDetails summary="pt_source 분포" value={reconcile.pt_source_distribution} />
          ) : null}
          {reconcile.warnings && reconcile.warnings.length > 0 ? (
            <IssueList items={reconcile.warnings} title="warnings" tone="warn" />
          ) : null}
        </>
      ) : null}
    </div>
  );
}
