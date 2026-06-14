"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { postJson, requestJson } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import {
  reconcileIssueLabels,
  sourceFilesPaths,
  type ReconcileResolveAction,
  type SourceCapacityUsage,
  type SourceReconcileItem,
  type SourceReconcileItemPage,
  type SourceReconcileRun
} from "@/lib/source-files";

const EMPTY_RUNS: SourceReconcileRun[] = [];
const EMPTY_ITEMS: SourceReconcileItem[] = [];

// Resolve actions allowed without extra required body fields (doc ~1458-1479).
// `import_object`, `extend_registration_deadline`, `delete_object`,
// `retry_delete_object` and `update_hash_after_verify` need extra inputs/roles,
// so the simple inline buttons cover the no-extra-input resolves.
const SIMPLE_RESOLVE_ACTIONS: ReconcileResolveAction[] = [
  "mark_db_missing",
  "soft_delete_db_row",
  "restore_soft_deleted"
];

export function ReconcileTab() {
  const queryClient = useQueryClient();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [mode, setMode] = useState<"quick" | "deep">("quick");
  const [lastResult, setLastResult] = useState<unknown>(null);

  const { data: runs = EMPTY_RUNS, refetch: refetchRuns } = useQuery({
    queryKey: ["reconcile-runs"],
    queryFn: () => requestJson<SourceReconcileRun[]>(sourceFilesPaths.reconcileList())
  });
  const effectiveRunId = selectedRunId ?? runs[0]?.source_storage_reconcile_run_id ?? null;

  const { data: itemPage } = useQuery({
    queryKey: ["reconcile-items", effectiveRunId],
    queryFn: () =>
      requestJson<SourceReconcileItemPage>(sourceFilesPaths.reconcileItems(effectiveRunId!)),
    enabled: effectiveRunId !== null
  });
  const items = itemPage?.items ?? EMPTY_ITEMS;

  const { data: capacity } = useQuery({
    queryKey: ["source-capacity"],
    queryFn: () => requestJson<SourceCapacityUsage>(sourceFilesPaths.capacity())
  });

  const runReconcile = useMutation({
    mutationFn: () => postJson<SourceReconcileRun>(sourceFilesPaths.reconcile(), { mode }),
    onSuccess: (run) => {
      setLastResult(run);
      setSelectedRunId(run.source_storage_reconcile_run_id);
      void queryClient.invalidateQueries({ queryKey: ["reconcile-runs"] });
    },
    onError: (error) => setLastResult({ error: error instanceof Error ? error.message : String(error) })
  });

  const resolveItem = useMutation({
    mutationFn: ({ itemId, action }: { itemId: string; action: ReconcileResolveAction }) =>
      postJson(sourceFilesPaths.reconcileItemResolve(itemId), { action }),
    onSuccess: (data) => {
      setLastResult(data);
      void queryClient.invalidateQueries({ queryKey: ["reconcile-items"] });
    },
    onError: (error) => setLastResult({ error: error instanceof Error ? error.message : String(error) })
  });

  return (
    <div className="source-stack">
      <Panel
        title="정합성 실행 (RustFS ⟷ DB)"
        actions={
          <div className="toolbar-inline">
            <select
              aria-label="reconcile 모드"
              onChange={(event) => setMode(event.target.value as "quick" | "deep")}
              value={mode}
            >
              <option value="quick">quick</option>
              <option value="deep">deep (전체 rehash)</option>
            </select>
            <button className="button" disabled={runReconcile.isPending} onClick={() => runReconcile.mutate()} type="button">
              <Play size={16} />
              실행
            </button>
            <button className="icon-button" onClick={() => void refetchRuns()} title="새로고침" type="button">
              <RefreshCw size={16} />
            </button>
          </div>
        }
      >
        <table className="table compact">
          <thead>
            <tr>
              <th>실행</th>
              <th>모드</th>
              <th>상태</th>
              <th>객체</th>
              <th>불일치</th>
              <th>해결</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr
                className={run.source_storage_reconcile_run_id === effectiveRunId ? "active-row" : ""}
                key={run.source_storage_reconcile_run_id}
              >
                <td>
                  <button
                    className="link-button"
                    onClick={() => setSelectedRunId(run.source_storage_reconcile_run_id)}
                    type="button"
                  >
                    {run.source_storage_reconcile_run_id.slice(0, 12)}…
                  </button>
                </td>
                <td>{run.mode}</td>
                <td>
                  <StatusBadge value={run.state} />
                </td>
                <td>{run.scanned_objects.toLocaleString()}</td>
                <td>{run.mismatch_count.toLocaleString()}</td>
                <td>{run.resolved_count.toLocaleString()}</td>
              </tr>
            ))}
            {runs.length === 0 ? (
              <tr>
                <td colSpan={6}>정합성 실행 기록이 없습니다.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </Panel>

      <Panel title="이슈 항목">
        {items.length === 0 ? (
          <p className="form-note">선택한 실행에 미해결 이슈가 없습니다.</p>
        ) : (
          <table className="table compact">
            <thead>
              <tr>
                <th>이슈 유형</th>
                <th>심각도</th>
                <th>상태</th>
                <th>객체 키</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.source_storage_reconcile_item_id}>
                  <td title={item.issue_type}>{reconcileIssueLabels[item.issue_type]}</td>
                  <td>
                    <StatusBadge value={item.severity} />
                  </td>
                  <td>{item.state}</td>
                  <td title={item.object_key ?? ""}>
                    {item.object_key ? `${item.object_key.slice(0, 24)}…` : "-"}
                  </td>
                  <td>
                    {item.state === "open" ? (
                      <div className="button-row">
                        {SIMPLE_RESOLVE_ACTIONS.map((action) => (
                          <button
                            className="button secondary"
                            disabled={resolveItem.isPending}
                            key={action}
                            onClick={() =>
                              resolveItem.mutate({
                                itemId: item.source_storage_reconcile_item_id,
                                action
                              })
                            }
                            type="button"
                          >
                            {action}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <span className="form-note">{item.resolution_action ?? "-"}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="용량 (capacity)">
        <CapacityPanel capacity={capacity} />
      </Panel>

      {lastResult ? (
        <Panel title="최근 결과">
          <pre className="json-box">{JSON.stringify(lastResult, null, 2)}</pre>
        </Panel>
      ) : null}
    </div>
  );
}

function CapacityPanel({ capacity }: { capacity?: SourceCapacityUsage }) {
  if (!capacity) {
    return <p className="form-note">용량 정보를 불러오는 중…</p>;
  }
  return (
    <>
      <dl className="criteria-grid">
        <div>
          <dt>전체 용량</dt>
          <dd>{formatBytes(capacity.total_bytes)}</dd>
        </div>
        <div>
          <dt>객체 수</dt>
          <dd>{capacity.total_object_count.toLocaleString()}</dd>
        </div>
        <div>
          <dt>한도 초과</dt>
          <dd>{capacity.over_threshold ? "예" : "아니오"}</dd>
        </div>
        <div>
          <dt>quarantine</dt>
          <dd>{formatBytes(capacity.quarantined_bytes)}</dd>
        </div>
      </dl>
      <table className="table compact">
        <thead>
          <tr>
            <th>카테고리</th>
            <th>객체</th>
            <th>용량</th>
            <th>soft-delete</th>
          </tr>
        </thead>
        <tbody>
          {capacity.categories.map((row) => (
            <tr key={row.category}>
              <td>{row.category}</td>
              <td>{row.object_count.toLocaleString()}</td>
              <td>{formatBytes(row.total_bytes)}</td>
              <td>{formatBytes(row.soft_deleted_bytes)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
