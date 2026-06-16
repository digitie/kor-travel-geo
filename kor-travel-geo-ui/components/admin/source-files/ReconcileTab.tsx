"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { RoleRequirementNote } from "@/components/admin/RoleRequirementNote";
import { RetentionWarning } from "@/components/admin/source-files/RetentionWarning";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { postJson, requestJson } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import {
  HARD_DELETE_CONFIRMATION,
  isBulkHardDeleteEligible,
  reconcileIssueLabels,
  sourceFilesPaths,
  type ReconcileResolveAction,
  type SourceBulkHardDeleteRequest,
  type SourceBulkHardDeleteResponse,
  type SourceCapacityUsage,
  type SourceHardDeleteOutcome,
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
  const [selectedKeys, setSelectedKeys] = useState<ReadonlySet<string>>(new Set());
  const [hardDeleteOpen, setHardDeleteOpen] = useState(false);

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

  // 정리 대상(미등록 stored object) — 수동 일괄 영구 삭제 (T-212, ADR-052).
  const cleanupTargets = useMemo(() => items.filter(isBulkHardDeleteEligible), [items]);
  const selectedTargets = useMemo(
    () => cleanupTargets.filter((item) => selectedKeys.has(item.object_key as string)),
    [cleanupTargets, selectedKeys]
  );

  // 다른 실행을 선택하면 선택 상태를 초기화한다(stale object_key 방지).
  useEffect(() => {
    setSelectedKeys(new Set());
    setHardDeleteOpen(false);
  }, [effectiveRunId]);

  const bulkHardDelete = useMutation({
    mutationFn: (body: SourceBulkHardDeleteRequest) =>
      postJson<SourceBulkHardDeleteResponse>(sourceFilesPaths.bulkHardDelete(), body),
    onSuccess: (data) => {
      setLastResult(data);
      setSelectedKeys(new Set());
      setHardDeleteOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["reconcile-items"] });
      void queryClient.invalidateQueries({ queryKey: ["source-capacity"] });
    },
    onError: (error) => setLastResult({ error: error instanceof Error ? error.message : String(error) })
  });

  function toggleKey(objectKey: string): void {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(objectKey)) next.delete(objectKey);
      else next.add(objectKey);
      return next;
    });
  }

  function toggleAllTargets(checked: boolean): void {
    setSelectedKeys(
      checked ? new Set(cleanupTargets.map((item) => item.object_key as string)) : new Set()
    );
  }

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

      <Panel
        title="이슈 항목"
        actions={
          cleanupTargets.length > 0 ? (
            <div className="toolbar-inline">
              <span className="form-note">
                정리 대상 {cleanupTargets.length}건 · 선택 {selectedTargets.length}건
              </span>
              <button
                className="button danger"
                disabled={selectedTargets.length === 0 || bulkHardDelete.isPending}
                onClick={() => setHardDeleteOpen(true)}
                type="button"
              >
                <Trash2 size={16} />
                선택 항목 영구 삭제
              </button>
            </div>
          ) : null
        }
      >
        {items.length === 0 ? (
          <p className="form-note">선택한 실행에 미해결 이슈가 없습니다.</p>
        ) : (
          <table className="table compact">
            <thead>
              <tr>
                <th>
                  {cleanupTargets.length > 0 ? (
                    <input
                      aria-label="정리 대상 전체 선택"
                      checked={
                        selectedTargets.length > 0 &&
                        selectedTargets.length === cleanupTargets.length
                      }
                      onChange={(event) => toggleAllTargets(event.target.checked)}
                      type="checkbox"
                    />
                  ) : null}
                </th>
                <th>이슈 유형</th>
                <th>심각도</th>
                <th>상태</th>
                <th>객체 키</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const eligible = isBulkHardDeleteEligible(item);
                const objectKey = item.object_key ?? "";
                return (
                  <tr key={item.source_storage_reconcile_item_id}>
                    <td>
                      {eligible ? (
                        <input
                          aria-label={`정리 대상 선택: ${objectKey}`}
                          checked={selectedKeys.has(objectKey)}
                          onChange={() => toggleKey(objectKey)}
                          type="checkbox"
                        />
                      ) : null}
                    </td>
                    <td title={item.issue_type}>{reconcileIssueLabels[item.issue_type]}</td>
                    <td>
                      <StatusBadge value={item.severity} />
                    </td>
                    <td>{item.state}</td>
                    <td title={objectKey}>
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
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="용량 (capacity)">
        <CapacityPanel capacity={capacity} />
      </Panel>

      {lastResult ? (
        <Panel title="최근 결과">
          {isBulkDeleteResult(lastResult) ? (
            <BulkDeleteResultSummary result={lastResult} />
          ) : (
            <pre className="json-box">{JSON.stringify(lastResult, null, 2)}</pre>
          )}
        </Panel>
      ) : null}

      {hardDeleteOpen ? (
        <BulkHardDeleteDialog
          objectKeys={selectedTargets.map((item) => item.object_key as string)}
          onCancel={() => setHardDeleteOpen(false)}
          onConfirm={(body) => bulkHardDelete.mutate(body)}
          pending={bulkHardDelete.isPending}
        />
      ) : null}
    </div>
  );
}

function BulkHardDeleteDialog({
  objectKeys,
  onCancel,
  onConfirm,
  pending
}: {
  objectKeys: string[];
  onCancel: () => void;
  onConfirm: (body: SourceBulkHardDeleteRequest) => void;
  pending: boolean;
}) {
  const [confirmation, setConfirmation] = useState("");
  const [manifestAck, setManifestAck] = useState(false);
  const [reason, setReason] = useState("");
  const confirmationOk = confirmation === HARD_DELETE_CONFIRMATION;

  return (
    <div className="modal-backdrop">
      <div className="modal" role="dialog" aria-modal="true" aria-label="원천 객체 영구 삭제">
        <h2>정리 대상 {objectKeys.length}건 영구 삭제</h2>
        <p className="form-note warn">
          선택한 미등록 stored object를 RustFS에서 영구(hard) 삭제합니다. 되돌릴 수 없습니다.
          활성 정본이 참조하는 객체는 백엔드 가드로 자동 제외(skip)됩니다.
        </p>
        <RoleRequirementNote roles={["destructive_admin"]} />
        <ul className="key-list">
          {objectKeys.slice(0, 8).map((key) => (
            <li key={key} title={key}>
              {key}
            </li>
          ))}
          {objectKeys.length > 8 ? (
            <li className="form-note">… 외 {objectKeys.length - 8}건</li>
          ) : null}
        </ul>
        <label className="checkbox-row">
          <input
            checked={manifestAck}
            onChange={(event) => setManifestAck(event.target.checked)}
            type="checkbox"
          />
          완료된 db_backup manifest 없이 진행함을 확인 (manifest_ack)
        </label>
        <label className="field">
          <span>사유 (reason)</span>
          <input onChange={(event) => setReason(event.target.value)} value={reason} />
        </label>
        <div className="confirm-box">
          <label>확인 문구 입력: {HARD_DELETE_CONFIRMATION}</label>
          <input
            aria-label="hard-delete 확인 문구"
            onChange={(event) => setConfirmation(event.target.value)}
            placeholder={HARD_DELETE_CONFIRMATION}
            value={confirmation}
          />
          {!confirmationOk ? (
            <p className="form-note warn">확인 문구가 일치해야 합니다.</p>
          ) : null}
        </div>
        <div className="button-row">
          <button
            className="button danger"
            disabled={!confirmationOk || objectKeys.length === 0 || pending}
            onClick={() =>
              onConfirm({
                object_keys: objectKeys,
                typed_confirmation: confirmation,
                manifest_ack: manifestAck,
                reason: reason || null
              })
            }
            type="button"
          >
            <Trash2 size={16} />
            영구 삭제 실행
          </button>
          <button className="button secondary" disabled={pending} onClick={onCancel} type="button">
            취소
          </button>
        </div>
      </div>
    </div>
  );
}

function CapacityPanel({ capacity }: { capacity?: SourceCapacityUsage }) {
  if (!capacity) {
    return <p className="form-note">용량 정보를 불러오는 중…</p>;
  }
  return (
    <>
      <RetentionWarning retention={capacity.retention} />
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

function isBulkDeleteResult(value: unknown): value is SourceBulkHardDeleteResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "hard_deleted_count" in value &&
    "requested_count" in value
  );
}

function BulkDeleteResultSummary({ result }: { result: SourceBulkHardDeleteResponse }) {
  const failed = (result.results ?? []).filter(
    (r: SourceHardDeleteOutcome) => r.outcome === "delete_failed"
  );
  return (
    <div className="source-stack">
      <dl className="criteria-grid">
        <div>
          <dt>요청</dt>
          <dd>{result.requested_count.toLocaleString()}건</dd>
        </div>
        <div>
          <dt>영구 삭제</dt>
          <dd>{result.hard_deleted_count.toLocaleString()}건</dd>
        </div>
        <div>
          <dt>삭제 실패</dt>
          <dd>{result.delete_failed_count.toLocaleString()}건</dd>
        </div>
        <div>
          <dt>건너뜀(skip)</dt>
          <dd>{result.skipped_count.toLocaleString()}건</dd>
        </div>
      </dl>
      {result.affected_match_set_ids && result.affected_match_set_ids.length > 0 ? (
        <p className="form-note">
          영향받은 match set: {result.affected_match_set_ids.join(", ")}
        </p>
      ) : null}
      {failed.length > 0 ? (
        <>
          <p className="form-note warn">삭제 실패 객체 (후속 확인 필요):</p>
          <ul className="key-list">
            {failed.map((r: SourceHardDeleteOutcome) => (
              <li key={r.object_key} title={r.reason ?? ""}>
                {r.object_key}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
