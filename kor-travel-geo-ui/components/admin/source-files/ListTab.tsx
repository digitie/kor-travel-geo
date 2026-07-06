"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Trash2, Link2, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { ActionResultPanel } from "@/components/admin/shared/ActionResultPanel";
import { ConfirmActionDialog } from "@/components/admin/shared/ConfirmActionDialog";
import { EmptyState } from "@/components/admin/shared/EmptyState";
import { RefreshButton } from "@/components/admin/shared/RefreshButton";
import { CapacitySummaryCard } from "@/components/admin/source-files/CapacitySummaryCard";
import { MatchSetItemsTable } from "@/components/admin/source-files/MatchSetItemsTable";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { type VirtualColumn, VirtualTable } from "@/components/ui/VirtualTable";
import { getErrorMessage, postJson, requestJson } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { toast } from "@/lib/toast";
import {
  sourceFilesPaths,
  type SourceMatchSet,
  type SourceMatchSetDetail,
  type SourceMatchSetItem,
  type UploadSessionStatus
} from "@/lib/source-files";

const EMPTY_SESSIONS: UploadSessionStatus[] = [];

type GroupAction = "soft-delete" | "restore" | "relink" | "validate";

const GROUP_ACTION_LABELS: Record<GroupAction, string> = {
  validate: "재검증",
  relink: "재연결(relink)",
  restore: "복원",
  "soft-delete": "soft-delete"
};

/**
 * There is no dedicated list-groups endpoint; registered source file groups are
 * surfaced from registered upload sessions (which carry ``source_file_group_id``,
 * state, validation, category, user_yyyymm, sizes) plus the categories referenced
 * by match-set items. Integrity-related state (the session lifecycle state +
 * registration state) is shown per row.
 */
type GroupRow = {
  groupId: string;
  category: string;
  userYyyymm: string;
  state: string;
  registrationState: string;
  groupKind: string;
  uploadedFileCount: number;
  expectedFileCount: number;
  maxBytes: number;
  source: "upload" | "match-set";
};

const GROUP_STATIC_COLUMNS: VirtualColumn<GroupRow>[] = [
  {
    key: "groupId",
    header: "그룹 ID",
    cell: (row) => <span title={row.groupId}>{row.groupId.slice(0, 12)}…</span>
  },
  { key: "category", header: "카테고리", cell: (row) => row.category },
  { key: "userYyyymm", header: "기준월", cell: (row) => row.userYyyymm },
  { key: "state", header: "상태(무결성)", cell: (row) => <StatusBadge value={row.state} /> },
  { key: "registrationState", header: "등록 상태", cell: (row) => row.registrationState },
  { key: "groupKind", header: "종류", cell: (row) => row.groupKind },
  {
    key: "fileCount",
    header: "파일 수",
    cell: (row) => `${row.uploadedFileCount}/${row.expectedFileCount}`
  },
  {
    key: "maxBytes",
    header: "크기 한도",
    cell: (row) => (row.maxBytes ? formatBytes(row.maxBytes) : "-")
  }
];

export function ListTab() {
  const queryClient = useQueryClient();
  const [lastResult, setLastResult] = useState<unknown>(null);

  const { data: sessions = EMPTY_SESSIONS, refetch } = useQuery({
    queryKey: ["upload-sessions", "all"],
    queryFn: () => requestJson<UploadSessionStatus[]>(sourceFilesPaths.uploadSessionsList())
  });
  const { data: matchSets = [] } = useQuery({
    queryKey: ["source-match-sets"],
    queryFn: () => requestJson<SourceMatchSet[]>(sourceFilesPaths.matchSets())
  });

  const rows = useMemo(() => buildGroupRows(sessions), [sessions]);

  const groupAction = useMutation({
    mutationFn: ({ groupId, action }: { groupId: string; action: GroupAction }) => {
      switch (action) {
        case "soft-delete":
          return postJson(sourceFilesPaths.groupSoftDelete(groupId), {});
        case "restore":
          return postJson(sourceFilesPaths.groupRestore(groupId), {});
        case "relink":
          return postJson(sourceFilesPaths.groupRelink(groupId), {});
        case "validate":
          return postJson(sourceFilesPaths.groupValidate(groupId), {});
        default:
          throw new Error(`unknown action: ${action satisfies never}`);
      }
    },
    onSuccess: (data, variables) => {
      toast.success(`${GROUP_ACTION_LABELS[variables.action]} 요청 완료`);
      setLastResult(data);
      void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["source-match-sets"] });
    },
    onError: (error, variables) => {
      const message = getErrorMessage(error);
      toast.error(`${GROUP_ACTION_LABELS[variables.action]} 실패`, message);
      setLastResult({ error: message });
    }
  });
  const { isPending: groupActionPending, mutate: mutateGroupAction } = groupAction;

  const groupColumns = useMemo<VirtualColumn<GroupRow>[]>(
    () => [
      ...GROUP_STATIC_COLUMNS,
      {
        key: "actions",
        header: "작업",
        cell: (row) => (
          <div className="button-row">
            <ConfirmActionDialog
              trigger={
                <Button
                  aria-label="재검증"
                  disabled={groupActionPending}
                  size="icon-sm"
                  title="재검증"
                  type="button"
                  variant="outline"
                >
                  <ShieldCheck aria-hidden="true" />
                </Button>
              }
              title="원천 그룹 재검증"
              description={`${row.category} · ${row.userYyyymm} 그룹의 구조 검증을 다시 실행합니다.`}
              destructive={false}
              confirmLabel="재검증 실행"
              onConfirm={() => mutateGroupAction({ groupId: row.groupId, action: "validate" })}
            />
            <ConfirmActionDialog
              trigger={
                <Button
                  aria-label="재연결"
                  disabled={groupActionPending}
                  size="icon-sm"
                  title="재연결 (백업 복원 그룹 relink)"
                  type="button"
                  variant="outline"
                >
                  <Link2 aria-hidden="true" />
                </Button>
              }
              title="그룹 재연결 (relink)"
              description={`${row.category} · ${row.userYyyymm} 그룹(백업 복원)을 현재 저장소 객체와 다시 연결합니다.`}
              destructive={false}
              confirmLabel="재연결 실행"
              onConfirm={() => mutateGroupAction({ groupId: row.groupId, action: "relink" })}
            />
            <ConfirmActionDialog
              trigger={
                <Button
                  aria-label="복원"
                  disabled={groupActionPending}
                  size="icon-sm"
                  title="복원 (soft-delete 취소)"
                  type="button"
                  variant="outline"
                >
                  <RotateCcw aria-hidden="true" />
                </Button>
              }
              title="soft-delete 복원"
              description={`${row.category} · ${row.userYyyymm} 그룹의 soft-delete를 취소하고 복원합니다.`}
              destructive={false}
              confirmLabel="복원 실행"
              onConfirm={() => mutateGroupAction({ groupId: row.groupId, action: "restore" })}
            />
            <ConfirmActionDialog
              trigger={
                <Button
                  aria-label="soft-delete"
                  disabled={groupActionPending}
                  size="icon-sm"
                  title="soft-delete"
                  type="button"
                  variant="outline"
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              }
              title="그룹 soft-delete"
              description={`${row.category} · ${row.userYyyymm} 그룹을 soft-delete 상태로 표시합니다. 복원으로 되돌릴 수 있습니다.`}
              confirmLabel="soft-delete 실행"
              onConfirm={() => mutateGroupAction({ groupId: row.groupId, action: "soft-delete" })}
            />
          </div>
        )
      }
    ],
    [groupActionPending, mutateGroupAction]
  );

  return (
    <div className="source-stack">
      <CapacitySummaryCard />

      <Panel
        title="원천 파일 그룹"
        actions={<RefreshButton iconOnly onClick={() => void refetch()} />}
      >
        <VirtualTable
          as="table"
          columns={groupColumns}
          emptyHint="등록된 원천 파일 그룹이 없습니다."
          rowKey={(row) => row.groupId}
          rows={rows}
        />
      </Panel>

      <Panel title="매칭 세트가 참조하는 카테고리">
        <MatchSetCategorySummary matchSets={matchSets} />
      </Panel>

      <ActionResultPanel result={lastResult} />
    </div>
  );
}

function MatchSetCategorySummary({ matchSets }: { matchSets: SourceMatchSet[] }) {
  const active = matchSets.find((set) => set.state === "active");
  const { data: detail } = useQuery({
    queryKey: ["source-match-set", active?.source_match_set_id],
    queryFn: () => requestJson<SourceMatchSetDetail>(sourceFilesPaths.matchSet(active!.source_match_set_id)),
    enabled: Boolean(active?.source_match_set_id)
  });

  if (!active) {
    return <EmptyState>활성 매칭 세트가 없습니다.</EmptyState>;
  }
  const items: SourceMatchSetItem[] = detail?.items ?? [];
  return <MatchSetItemsTable items={items} variant="summary" />;
}

function buildGroupRows(sessions: UploadSessionStatus[]): GroupRow[] {
  const byGroup = new Map<string, GroupRow>();
  for (const session of sessions) {
    if (!session.source_file_group_id) continue;
    // Prefer the most recently updated session per group id.
    const existing = byGroup.get(session.source_file_group_id);
    if (existing) continue;
    byGroup.set(session.source_file_group_id, {
      groupId: session.source_file_group_id,
      category: session.category,
      userYyyymm: session.user_yyyymm,
      state: session.state,
      registrationState: session.registration_state,
      groupKind: session.group_kind,
      uploadedFileCount: session.uploaded_file_count,
      expectedFileCount: session.expected_file_count,
      maxBytes: session.max_bytes,
      source: "upload"
    });
  }
  return Array.from(byGroup.values());
}
