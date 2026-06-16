"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { type OpsArtifact, type RestoreReconcileResult, requestJson } from "@/lib/api";

/**
 * Extract the T-233 ``row_count_verification`` reconcile block from a ``db_restore_log``
 * artifact manifest. Returns null for legacy restore logs that predate T-233.
 */
export function reconcileFromManifest(
  manifest: Record<string, unknown> | undefined
): RestoreReconcileResult | null {
  const block = manifest?.["row_count_verification"];
  if (!block || typeof block !== "object") return null;
  return block as RestoreReconcileResult;
}

/**
 * Post-restore reconcile results (T-253): lists recent ``db_restore_log`` artifacts and, for
 * each, surfaces the T-233 row/MV/sppn/pt_source/source_set PASS/FAIL plus warnings. Restore
 * logs that predate T-233 (no row_count_verification) are shown as "reconcile 없음".
 */
export function RestoreReconcilePanel() {
  const [rows, setRows] = useState<OpsArtifact[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const arts = await requestJson<OpsArtifact[]>(
        "/admin/ops/artifacts?artifact_type=db_restore_log&limit=20"
      );
      setRows(arts);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Panel
      title="복원 reconcile 결과"
      actions={
        <button className="button secondary" onClick={() => void load()} type="button">
          <RefreshCw size={16} />
          새로고침
        </button>
      }
    >
      {error ? (
        <p className="wizard-error" role="alert">
          {error}
        </p>
      ) : null}
      {rows.length === 0 ? (
        <p className="wizard-hint">복원 기록이 없습니다. [복원] 위저드로 복원을 실행하세요.</p>
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
    reconcile?.target_database ?? text(artifact.manifest?.["target_database"]) ?? "—";
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
        대상 DB: {String(target)} · {artifact.created_at.slice(0, 19).replace("T", " ")}
      </p>
      {reconcile ? (
        <>
          {reconcile.row_count_diffs && reconcile.row_count_diffs.length > 0 ? (
            <table className="table reconcile-table">
              <thead>
                <tr>
                  <th>object</th>
                  <th>expected</th>
                  <th>actual</th>
                  <th>match</th>
                </tr>
              </thead>
              <tbody>
                {reconcile.row_count_diffs.map((d) => (
                  <tr key={d.object}>
                    <td>{d.object}</td>
                    <td>{d.expected ?? "—"}</td>
                    <td>{d.actual}</td>
                    <td>
                      <StatusBadge
                        tone={d.match ? "ok" : "error"}
                        value={d.match ? "ok" : "mismatch"}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          <ul className="manifest-kv">
            <li>
              MV non-empty:{" "}
              {reconcile.mv_nonempty_ok === true ? "✅" : reconcile.mv_nonempty_ok === false ? "❌" : "—"}{" "}
              · mv_target {reconcile.mv_geocode_target_rows ?? "—"} / mv_text{" "}
              {reconcile.mv_geocode_text_search_rows ?? "—"}
            </li>
            <li>sppn: {reconcile.sppn_rows ?? "—"}</li>
          </ul>
          {reconcile.pt_source_distribution ? (
            <details className="reconcile-detail">
              <summary>pt_source 분포</summary>
              <JsonBlock value={reconcile.pt_source_distribution} />
            </details>
          ) : null}
          {reconcile.warnings && reconcile.warnings.length > 0 ? (
            <div className="wizard-list warn">
              <strong>warnings</strong>
              <ul>
                {reconcile.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function text(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}
