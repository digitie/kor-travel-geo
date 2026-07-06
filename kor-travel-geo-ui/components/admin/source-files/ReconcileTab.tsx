"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Trash2 } from "lucide-react";
import { useCallback, useId, useMemo, useReducer, useRef, useState } from "react";
import { ActionResultPanel } from "@/components/admin/shared/ActionResultPanel";
import { HelpTip } from "@/components/admin/shared/HelpTip";
import { KeyValueGrid } from "@/components/admin/shared/KeyValueGrid";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { TypedConfirmField } from "@/components/admin/shared/TypedConfirmField";
import { RoleRequirementNote } from "@/components/admin/RoleRequirementNote";
import { RetentionWarning } from "@/components/admin/source-files/RetentionWarning";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import { getErrorMessage, postJson, requestJson } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { toast } from "@/lib/toast";
import {
  HARD_DELETE_CONFIRMATION,
  isBulkHardDeleteEligible,
  reconcileIssueLabels,
  sourceFilesPaths,
  type ReconcileResolveAction,
  type SourceBulkHardDeleteRequest,
  type SourceBulkHardDeleteResponse,
  type SourceCapacityUsage,
  type SourceCategoryCapacity,
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

type ReconcileViewState = {
  selectedRunId: string | null;
  mode: "quick" | "deep";
  lastResult: unknown;
  selectedKeys: ReadonlySet<string>;
  hardDeleteOpen: boolean;
};

type ReconcileViewAction =
  | { type: "set-mode"; mode: "quick" | "deep" }
  | { type: "select-run"; runId: string }
  | { type: "set-last-result"; result: unknown }
  | { type: "toggle-key"; objectKey: string }
  | { type: "set-all-keys"; objectKeys: string[] }
  | { type: "open-hard-delete" }
  | { type: "close-hard-delete" }
  | { type: "hard-delete-succeeded"; result: SourceBulkHardDeleteResponse };

const INITIAL_RECONCILE_VIEW_STATE: ReconcileViewState = {
  selectedRunId: null,
  mode: "quick",
  lastResult: null,
  selectedKeys: new Set(),
  hardDeleteOpen: false
};

function reconcileViewReducer(
  state: ReconcileViewState,
  action: ReconcileViewAction
): ReconcileViewState {
  switch (action.type) {
    case "set-mode":
      return { ...state, mode: action.mode };
    case "select-run":
      return {
        ...state,
        selectedRunId: action.runId,
        selectedKeys: new Set(),
        hardDeleteOpen: false
      };
    case "set-last-result":
      return { ...state, lastResult: action.result };
    case "toggle-key": {
      const selectedKeys = new Set(state.selectedKeys);
      if (selectedKeys.has(action.objectKey)) selectedKeys.delete(action.objectKey);
      else selectedKeys.add(action.objectKey);
      return { ...state, selectedKeys };
    }
    case "set-all-keys":
      return { ...state, selectedKeys: new Set(action.objectKeys) };
    case "open-hard-delete":
      return { ...state, hardDeleteOpen: true };
    case "close-hard-delete":
      return { ...state, hardDeleteOpen: false };
    case "hard-delete-succeeded":
      return {
        ...state,
        lastResult: action.result,
        selectedKeys: new Set(),
        hardDeleteOpen: false
      };
  }
}

export function ReconcileTab() {
  const queryClient = useQueryClient();
  const [viewState, dispatchView] = useReducer(
    reconcileViewReducer,
    INITIAL_RECONCILE_VIEW_STATE
  );
  const { selectedRunId, mode, lastResult, selectedKeys, hardDeleteOpen } = viewState;

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
      toast.success("정합성 실행을 시작했습니다");
      dispatchView({ type: "set-last-result", result: run });
      dispatchView({ type: "select-run", runId: run.source_storage_reconcile_run_id });
      void queryClient.invalidateQueries({ queryKey: ["reconcile-runs"] });
    },
    onError: (error) => {
      const message = getErrorMessage(error);
      toast.error("정합성 실행 실패", message);
      dispatchView({ type: "set-last-result", result: { error: message } });
    }
  });

  const resolveItem = useMutation({
    mutationFn: ({ itemId, action }: { itemId: string; action: ReconcileResolveAction }) =>
      postJson(sourceFilesPaths.reconcileItemResolve(itemId), { action }),
    onSuccess: (data) => {
      toast.success("이슈를 처리했습니다");
      dispatchView({ type: "set-last-result", result: data });
      void queryClient.invalidateQueries({ queryKey: ["reconcile-items"] });
    },
    onError: (error) => {
      const message = getErrorMessage(error);
      toast.error("이슈 처리 실패", message);
      dispatchView({ type: "set-last-result", result: { error: message } });
    }
  });
  const { isPending: resolvePending, mutate: resolveMutate } = resolveItem;

  // 정리 대상(미등록 stored object) — 수동 일괄 영구 삭제 (T-212, ADR-052).
  const cleanupTargets = useMemo(() => items.filter(isBulkHardDeleteEligible), [items]);
  const selectedTargets = useMemo(
    () => cleanupTargets.filter((item) => selectedKeys.has(item.object_key as string)),
    [cleanupTargets, selectedKeys]
  );

  const bulkHardDelete = useMutation({
    mutationFn: (body: SourceBulkHardDeleteRequest) =>
      postJson<SourceBulkHardDeleteResponse>(sourceFilesPaths.bulkHardDelete(), body),
    onSuccess: (data) => {
      toast.success(`영구 삭제 완료 — ${data.hard_deleted_count.toLocaleString()}건`);
      dispatchView({ type: "hard-delete-succeeded", result: data });
      void queryClient.invalidateQueries({ queryKey: ["reconcile-items"] });
      void queryClient.invalidateQueries({ queryKey: ["source-capacity"] });
    },
    onError: (error) => {
      const message = getErrorMessage(error);
      toast.error("영구 삭제 실패", message);
      dispatchView({ type: "set-last-result", result: { error: message } });
    }
  });

  const toggleKey = useCallback((objectKey: string): void => {
    dispatchView({ type: "toggle-key", objectKey });
  }, []);

  const toggleAllTargets = useCallback(
    (checked: boolean): void => {
      dispatchView({
        type: "set-all-keys",
        objectKeys: checked ? cleanupTargets.map((item) => item.object_key as string) : []
      });
    },
    [cleanupTargets]
  );
  const selectRun = useCallback((runId: string) => {
    dispatchView({ type: "select-run", runId });
  }, []);
  const setMode = useCallback((nextMode: "quick" | "deep") => {
    dispatchView({ type: "set-mode", mode: nextMode });
  }, []);
  const openHardDelete = useCallback(() => {
    dispatchView({ type: "open-hard-delete" });
  }, []);
  const resolveOpenItem = useCallback(
    (itemId: string, action: ReconcileResolveAction) => {
      resolveMutate({ itemId, action });
    },
    [resolveMutate]
  );

  return (
    <div className="source-stack">
      <ReconcileRunsPanel
        effectiveRunId={effectiveRunId}
        mode={mode}
        onModeChange={setMode}
        onRefresh={() => void refetchRuns()}
        onRun={() => runReconcile.mutate()}
        onSelectRun={selectRun}
        pending={runReconcile.isPending}
        runs={runs}
      />

      <ReconcileItemsPanel
        bulkPending={bulkHardDelete.isPending}
        cleanupTargets={cleanupTargets}
        items={items}
        onOpenHardDelete={openHardDelete}
        onResolve={resolveOpenItem}
        onToggleAllTargets={toggleAllTargets}
        onToggleKey={toggleKey}
        resolvePending={resolvePending}
        selectedKeys={selectedKeys}
        selectedTargets={selectedTargets}
      />

      <Panel
        title="용량"
        badges={
          <HelpTip label="용량 도움말">
            원천 저장소(capacity) 사용량 — 카테고리별 객체 수와 바이트, soft-delete·격리 용량을
            보여 줍니다.
          </HelpTip>
        }
      >
        <CapacityPanel capacity={capacity} />
      </Panel>

      {isBulkDeleteResult(lastResult) ? (
        <Panel title="최근 결과">
          <BulkDeleteResultSummary result={lastResult} />
        </Panel>
      ) : (
        <ActionResultPanel result={lastResult} />
      )}

      <BulkHardDeleteDialog
        objectKeys={selectedTargets.map((item) => item.object_key as string)}
        onClose={() => dispatchView({ type: "close-hard-delete" })}
        onConfirm={(body) => bulkHardDelete.mutate(body)}
        open={hardDeleteOpen}
        pending={bulkHardDelete.isPending}
      />
    </div>
  );
}

function ReconcileRunsPanel({
  effectiveRunId,
  mode,
  onModeChange,
  onRefresh,
  onRun,
  onSelectRun,
  pending,
  runs
}: {
  effectiveRunId: string | null;
  mode: "quick" | "deep";
  onModeChange: (mode: "quick" | "deep") => void;
  onRefresh: () => void;
  onRun: () => void;
  onSelectRun: (runId: string) => void;
  pending: boolean;
  runs: SourceReconcileRun[];
}) {
  const runColumns = useMemo<VirtualColumn<SourceReconcileRun>[]>(
    () => [
      {
        key: "run",
        header: "실행",
        cell: (run) => (
          <Button
            onClick={() => onSelectRun(run.source_storage_reconcile_run_id)}
            size="xs"
            type="button"
            variant="link"
          >
            {run.source_storage_reconcile_run_id.slice(0, 12)}…
          </Button>
        )
      },
      { key: "mode", header: "모드", cell: (run) => run.mode },
      { key: "state", header: "상태", cell: (run) => <StatusBadge value={run.state} /> },
      { key: "scanned", header: "객체", cell: (run) => run.scanned_objects.toLocaleString() },
      { key: "mismatch", header: "불일치", cell: (run) => run.mismatch_count.toLocaleString() },
      { key: "resolved", header: "해결", cell: (run) => run.resolved_count.toLocaleString() }
    ],
    [onSelectRun]
  );

  return (
    <Panel
      title="정합성 실행"
      badges={
        <HelpTip label="정합성 실행 도움말">
          RustFS 저장소 객체와 DB 등록 정보를 비교(RustFS ⟷ DB)해 불일치 이슈를 찾습니다. deep
          모드는 모든 객체를 다시 해시하므로 오래 걸리고 저장소 부하가 큽니다.
        </HelpTip>
      }
      actions={
        <div className="toolbar-inline">
          <div className="w-56 shrink-0">
            <NativeSelect
              aria-label="reconcile 모드"
              onChange={(event) => onModeChange(event.target.value as "quick" | "deep")}
              value={mode}
            >
              <option value="quick">quick — 빠른 비교</option>
              <option value="deep">deep — 전체 rehash (느림)</option>
            </NativeSelect>
          </div>
          <Button disabled={pending} onClick={onRun} type="button">
            <Play aria-hidden="true" />
            실행
          </Button>
          <RefreshButton iconOnly onClick={onRefresh} />
        </div>
      }
    >
      <VirtualTable
        as="table"
        columns={runColumns}
        compact
        emptyHint="정합성 실행 기록이 없습니다."
        getRowClassName={(run) =>
          run.source_storage_reconcile_run_id === effectiveRunId ? "active-row" : undefined
        }
        rowKey={(run) => run.source_storage_reconcile_run_id}
        rows={runs}
      />
    </Panel>
  );
}

function ReconcileItemsPanel({
  bulkPending,
  cleanupTargets,
  items,
  onOpenHardDelete,
  onResolve,
  onToggleAllTargets,
  onToggleKey,
  resolvePending,
  selectedKeys,
  selectedTargets
}: {
  bulkPending: boolean;
  cleanupTargets: SourceReconcileItem[];
  items: SourceReconcileItem[];
  onOpenHardDelete: () => void;
  onResolve: (itemId: string, action: ReconcileResolveAction) => void;
  onToggleAllTargets: (checked: boolean) => void;
  onToggleKey: (objectKey: string) => void;
  resolvePending: boolean;
  selectedKeys: ReadonlySet<string>;
  selectedTargets: SourceReconcileItem[];
}) {
  const itemColumns = useMemo<VirtualColumn<SourceReconcileItem>[]>(
    () => [
      {
        key: "select",
        header: "",
        headerCell:
          cleanupTargets.length > 0 ? (
            <Checkbox
              aria-label="정리 대상 전체 선택"
              checked={
                selectedTargets.length > 0 && selectedTargets.length === cleanupTargets.length
                  ? true
                  : selectedTargets.length > 0
                    ? "indeterminate"
                    : false
              }
              onCheckedChange={(checked) => onToggleAllTargets(checked === true)}
            />
          ) : undefined,
        cell: (item) => {
          const eligible = isBulkHardDeleteEligible(item);
          const objectKey = item.object_key ?? "";
          return eligible ? (
            <Checkbox
              aria-label={`정리 대상 선택: ${objectKey}`}
              checked={selectedKeys.has(objectKey)}
              onCheckedChange={() => onToggleKey(objectKey)}
            />
          ) : null;
        }
      },
      {
        key: "issue_type",
        header: "이슈 유형",
        cell: (item) => (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>{reconcileIssueLabels[item.issue_type]}</span>
            </TooltipTrigger>
            <TooltipContent>{item.issue_type}</TooltipContent>
          </Tooltip>
        )
      },
      {
        key: "severity",
        header: "심각도",
        cell: (item) => <StatusBadge value={item.severity} />
      },
      { key: "state", header: "상태", cell: (item) => item.state },
      {
        key: "object_key",
        header: "객체 키",
        cell: (item) =>
          item.object_key ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>{`${item.object_key.slice(0, 24)}…`}</span>
              </TooltipTrigger>
              <TooltipContent className="break-all">{item.object_key}</TooltipContent>
            </Tooltip>
          ) : (
            "-"
          )
      },
      {
        key: "action",
        header: "작업",
        cell: (item) =>
          item.state === "open" ? (
            <div className="button-row">
              {SIMPLE_RESOLVE_ACTIONS.map((action) => (
                <Button
                  disabled={resolvePending}
                  key={action}
                  onClick={() => onResolve(item.source_storage_reconcile_item_id, action)}
                  size="xs"
                  type="button"
                  variant="outline"
                >
                  {action}
                </Button>
              ))}
            </div>
          ) : (
            <span className="form-note">{item.resolution_action ?? "-"}</span>
          )
      }
    ],
    [
      cleanupTargets.length,
      onResolve,
      onToggleAllTargets,
      onToggleKey,
      resolvePending,
      selectedKeys,
      selectedTargets.length
    ]
  );

  return (
    <Panel
      title="이슈 항목"
      actions={
        cleanupTargets.length > 0 ? (
          <div className="toolbar-inline">
            <span className="form-note">
              정리 대상 {cleanupTargets.length}건 · 선택 {selectedTargets.length}건
            </span>
            <Button
              data-hard-delete-trigger=""
              disabled={selectedTargets.length === 0 || bulkPending}
              onClick={onOpenHardDelete}
              type="button"
              variant="destructive"
            >
              <Trash2 aria-hidden="true" />
              선택 항목 영구 삭제
            </Button>
          </div>
        ) : null
      }
    >
      <VirtualTable
        as="table"
        columns={itemColumns}
        compact
        emptyHint="선택한 실행에 미해결 이슈가 없습니다."
        rowKey={(item) => item.source_storage_reconcile_item_id}
        rows={items}
      />
    </Panel>
  );
}

function BulkHardDeleteDialog({
  objectKeys,
  onClose,
  onConfirm,
  open,
  pending
}: {
  objectKeys: string[];
  onClose: () => void;
  onConfirm: (body: SourceBulkHardDeleteRequest) => void;
  open: boolean;
  pending: boolean;
}) {
  const [confirmation, setConfirmation] = useState("");
  const [manifestAck, setManifestAck] = useState(false);
  const [reason, setReason] = useState("");
  const confirmationOk = confirmation === HARD_DELETE_CONFIRMATION;
  const confirmBoxRef = useRef<HTMLDivElement>(null);
  const ackId = useId();
  const reasonId = useId();

  // 다이얼로그가 새로 열릴 때마다 확인 입력을 초기화한다. useEffect로 열림 후
  // 상태를 되돌리면 stale 프레임이 한 번 보이므로, open 전이를 렌더 중에 감지해
  // 초기화한다(React 권장 adjust-state-during-render).
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setConfirmation("");
      setManifestAck(false);
      setReason("");
    }
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      {/* 접근명은 spec 계약 문자열 aria-label로 고정 — radix 기본 aria-labelledby(제목)를 해제한다. */}
      <AlertDialogContent
        aria-label="원천 객체 영구 삭제"
        aria-labelledby={undefined}
        onOpenAutoFocus={(event) => {
          // 파괴적 다이얼로그: 열리면 확인 문구 입력에 바로 포커스를 둔다.
          event.preventDefault();
          confirmBoxRef.current?.querySelector("input")?.focus();
        }}
        onCloseAutoFocus={(event) => {
          // 컨트롤드 다이얼로그(트리거 없음)라 radix 기본 복귀가 없음 — 트리거 버튼으로 복귀.
          event.preventDefault();
          document
            .querySelector<HTMLElement>("[data-hard-delete-trigger]")
            ?.focus();
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle>정리 대상 {objectKeys.length}건 영구 삭제</AlertDialogTitle>
          <AlertDialogDescription>
            선택한 미등록 저장 객체를 RustFS에서 영구 삭제합니다. 되돌릴 수 없습니다. 활성 정본이
            참조하는 객체는 백엔드 가드가 자동 제외(skip)합니다.
          </AlertDialogDescription>
        </AlertDialogHeader>
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
        <div className="checkbox-row">
          <Checkbox
            checked={manifestAck}
            id={ackId}
            onCheckedChange={(checked) => setManifestAck(checked === true)}
          />
          <label className="m-0 text-sm" htmlFor={ackId}>
            완료된 db_backup manifest 없이 진행함을 확인
          </label>
          <HelpTip label="manifest 확인 도움말">
            API 필드 <code>manifest_ack</code> — 완료된 DB 백업 manifest 없이 영구 삭제를
            진행함을 확인하는 필수 항목입니다.
          </HelpTip>
        </div>
        <Field>
          <span className="flex items-center gap-1">
            <FieldLabel htmlFor={reasonId}>사유</FieldLabel>
            <HelpTip label="사유 도움말">
              API 필드 <code>reason</code> — 감사 기록에 남는 선택 입력입니다.
            </HelpTip>
          </span>
          <Input
            id={reasonId}
            onChange={(event) => setReason(event.target.value)}
            placeholder="예: 202605 재적재 전 저장소 정리"
            value={reason}
          />
        </Field>
        <div ref={confirmBoxRef}>
          <TypedConfirmField
            label="hard-delete 확인 문구"
            onChange={setConfirmation}
            phrase={HARD_DELETE_CONFIRMATION}
            value={confirmation}
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>취소</AlertDialogCancel>
          <AlertDialogAction
            disabled={!confirmationOk || !manifestAck || objectKeys.length === 0 || pending}
            onClick={() =>
              onConfirm({
                object_keys: objectKeys,
                typed_confirmation: confirmation,
                manifest_ack: manifestAck,
                reason: reason || null
              })
            }
            variant="destructive"
          >
            <Trash2 aria-hidden="true" />
            영구 삭제 실행
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

const CAPACITY_COLUMNS: VirtualColumn<SourceCategoryCapacity>[] = [
  { key: "category", header: "카테고리", cell: (row) => row.category },
  { key: "object_count", header: "객체", cell: (row) => row.object_count.toLocaleString() },
  { key: "total_bytes", header: "용량", cell: (row) => formatBytes(row.total_bytes) },
  {
    key: "soft_deleted_bytes",
    header: "soft-delete",
    cell: (row) => formatBytes(row.soft_deleted_bytes)
  }
];

function CapacityPanel({ capacity }: { capacity?: SourceCapacityUsage }) {
  if (!capacity) {
    return (
      <div className="grid gap-2">
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-4/5" />
        <Skeleton className="h-5 w-2/3" />
      </div>
    );
  }
  return (
    <>
      <RetentionWarning retention={capacity.retention} />
      <KeyValueGrid
        items={[
          { label: "전체 용량", value: formatBytes(capacity.total_bytes) },
          { label: "객체 수", value: capacity.total_object_count.toLocaleString() },
          { label: "한도 초과", value: capacity.over_threshold ? "예" : "아니오" },
          {
            label: "격리",
            value: formatBytes(capacity.quarantined_bytes),
            help: (
              <>
                API 필드 <code>quarantined_bytes</code> — 격리(quarantine)된 객체 용량입니다.
              </>
            ),
            helpLabel: "격리 도움말"
          }
        ]}
      />
      <VirtualTable
        as="table"
        columns={CAPACITY_COLUMNS}
        compact
        rowKey={(row) => row.category}
        rows={capacity.categories}
      />
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
      <KeyValueGrid
        items={[
          { label: "요청", value: `${result.requested_count.toLocaleString()}건` },
          { label: "영구 삭제", value: `${result.hard_deleted_count.toLocaleString()}건` },
          { label: "삭제 실패", value: `${result.delete_failed_count.toLocaleString()}건` },
          { label: "건너뜀(skip)", value: `${result.skipped_count.toLocaleString()}건` }
        ]}
      />
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
