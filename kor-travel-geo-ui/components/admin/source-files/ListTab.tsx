"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, RotateCcw, Trash2, Link2, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { CapacitySummaryCard } from "@/components/admin/source-files/CapacitySummaryCard";
import { Panel } from "@/components/ui/Panel";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { postJson, requestJson } from "@/lib/api";
import {
  sourceFilesPaths,
  sourceRoleLabel,
  type SourceMatchSet,
  type SourceMatchSetDetail,
  type SourceMatchSetItem,
  type UploadSessionStatus
} from "@/lib/source-files";

const EMPTY_SESSIONS: UploadSessionStatus[] = [];

type GroupAction = "soft-delete" | "restore" | "relink" | "validate";

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
    onSuccess: (data) => {
      setLastResult(data);
      void queryClient.invalidateQueries({ queryKey: ["upload-sessions"] });
      void queryClient.invalidateQueries({ queryKey: ["source-match-sets"] });
    },
    onError: (error) => setLastResult({ error: error instanceof Error ? error.message : String(error) })
  });

  return (
    <div className="source-stack">
      <CapacitySummaryCard />

      <Panel
        title="원천 파일 그룹"
        actions={
          <button className="icon-button" onClick={() => void refetch()} title="새로고침" type="button">
            <RefreshCw size={16} />
          </button>
        }
      >
        {rows.length === 0 ? (
          <p className="form-note">등록된 원천 파일 그룹이 없습니다.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>그룹 ID</th>
                <th>카테고리</th>
                <th>기준월</th>
                <th>상태(무결성)</th>
                <th>등록 상태</th>
                <th>종류</th>
                <th>파일 수</th>
                <th>크기 한도</th>
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.groupId}>
                  <td title={row.groupId}>{row.groupId.slice(0, 12)}…</td>
                  <td>{row.category}</td>
                  <td>{row.userYyyymm}</td>
                  <td>
                    <StatusBadge value={row.state} />
                  </td>
                  <td>{row.registrationState}</td>
                  <td>{row.groupKind}</td>
                  <td>
                    {row.uploadedFileCount}/{row.expectedFileCount}
                  </td>
                  <td>{formatMb(row.maxBytes)}</td>
                  <td>
                    <div className="button-row">
                      <button
                        className="icon-button"
                        disabled={groupAction.isPending}
                        onClick={() => groupAction.mutate({ groupId: row.groupId, action: "validate" })}
                        title="재검증"
                        type="button"
                      >
                        <ShieldCheck size={15} />
                      </button>
                      <button
                        className="icon-button"
                        disabled={groupAction.isPending}
                        onClick={() => groupAction.mutate({ groupId: row.groupId, action: "relink" })}
                        title="relink (백업 복원 그룹 재연결)"
                        type="button"
                      >
                        <Link2 size={15} />
                      </button>
                      <button
                        className="icon-button"
                        disabled={groupAction.isPending}
                        onClick={() => groupAction.mutate({ groupId: row.groupId, action: "restore" })}
                        title="복원 (soft-delete 취소)"
                        type="button"
                      >
                        <RotateCcw size={15} />
                      </button>
                      <button
                        className="icon-button"
                        disabled={groupAction.isPending}
                        onClick={() => groupAction.mutate({ groupId: row.groupId, action: "soft-delete" })}
                        title="soft-delete"
                        type="button"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="매칭 세트가 참조하는 카테고리">
        <MatchSetCategorySummary matchSets={matchSets} />
      </Panel>

      {lastResult ? (
        <Panel title="최근 결과">
          <pre className="json-box">{JSON.stringify(lastResult, null, 2)}</pre>
        </Panel>
      ) : null}
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
    return <p className="form-note">활성 매칭 세트가 없습니다.</p>;
  }
  const items: SourceMatchSetItem[] = detail?.items ?? [];
  return (
    <table className="table compact">
      <thead>
        <tr>
          <th>카테고리</th>
          <th>역할</th>
          <th>생략</th>
          <th>그룹 ID</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.source_match_set_item_id}>
            <td>{item.category}</td>
            <td>{sourceRoleLabel(item.role)}</td>
            <td>{item.omitted ? "생략" : "포함"}</td>
            <td>{item.source_file_group_id ? `${item.source_file_group_id.slice(0, 12)}…` : "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
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

function formatMb(bytes: number): string {
  if (!bytes) return "-";
  return `${(bytes / 1024 / 1024).toFixed(0)} MB`;
}
