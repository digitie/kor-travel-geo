import type { components } from "@/types/api.gen";

/** T-283 파일 관리 — 백엔드 통합 파일 인벤토리 계약 타입 (생성 타입 alias). */
export type FileInventoryItem = components["schemas"]["FileInventoryItem"];
export type FileInventoryPage = components["schemas"]["FileInventoryPage"];
export type FileInventorySummary = components["schemas"]["FileInventorySummary"];
export type FileInventorySourceDetail = components["schemas"]["FileInventorySourceDetail"];
export type FileInventoryUsage = components["schemas"]["FileInventoryUsage"];
export type FileInventoryFileInfo = components["schemas"]["FileInventoryFileInfo"];
export type FileInventorySessionInfo = components["schemas"]["FileInventorySessionInfo"];
export type FileInventoryIssue = components["schemas"]["FileInventoryIssue"];

export type FileInventoryKind = FileInventoryItem["file_kind"];

export const fileInventoryPaths = {
  list: (params: {
    kind?: string;
    category?: string;
    lifecycle?: string;
    temporaryOnly?: boolean;
    limit?: number;
  }) => {
    const query = new URLSearchParams();
    if (params.kind && params.kind !== "all") query.set("kind", params.kind);
    if (params.category) query.set("category", params.category);
    if (params.lifecycle) query.set("lifecycle", params.lifecycle);
    if (params.temporaryOnly) query.set("temporary_only", "true");
    if (params.limit) query.set("limit", String(params.limit));
    const text = query.toString();
    return `/admin/storage/files${text ? `?${text}` : ""}`;
  },
  sourceGroupDetail: (groupId: string) =>
    `/admin/storage/files/source-groups/${encodeURIComponent(groupId)}`
};

export const fileKindLabels: Record<string, string> = {
  source_group: "원천 파일",
  artifact: "백업/산출물",
  orphan_object: "저장소 객체"
};

export interface LifecycleMeta {
  label: string;
  tone: "ok" | "warn" | "error" | "info" | "neutral" | "brand";
  /** HelpTip에 쓰는 한 줄 설명. */
  hint: string;
}

/** lifecycle 버킷의 한국어 라벨·배지 톤·설명 (백엔드 core.file_inventory와 동기). */
const lifecycleMeta: Record<string, LifecycleMeta> = {
  serving: { label: "서빙 사용 중", tone: "ok", hint: "활성 매칭 세트에 포함되어 운영 DB 구성에 사용 중입니다." },
  staging: { label: "구성 대기", tone: "info", hint: "매칭 세트에 포함되어 있지만 아직 활성 세트는 아닙니다." },
  idle: { label: "미사용", tone: "neutral", hint: "등록은 됐지만 어떤 매칭 세트도 참조하지 않습니다." },
  in_progress: { label: "진행 중", tone: "warn", hint: "업로드 또는 검증이 진행 중인 임시 상태입니다." },
  unregistered: { label: "미등록", tone: "warn", hint: "저장은 됐지만 등록 기한이 지나 임시 상태로 남아 있습니다." },
  quarantined: { label: "격리", tone: "error", hint: "정합성 문제로 격리된 상태입니다." },
  missing: { label: "유실", tone: "error", hint: "DB 기록은 있으나 저장소에서 객체를 찾지 못했습니다." },
  soft_deleted: { label: "삭제 예정", tone: "neutral", hint: "soft-delete 상태 — 복원할 수 있습니다." },
  hard_deleted: { label: "영구 삭제됨", tone: "neutral", hint: "저장소에서 영구 삭제됐습니다." },
  delete_failed: { label: "삭제 실패", tone: "error", hint: "삭제 시도가 실패해 정리가 필요합니다." },
  available: { label: "보관 중", tone: "ok", hint: "사용 가능한 상태로 보관 중입니다." },
  creating: { label: "생성 중", tone: "warn", hint: "생성 작업이 진행 중입니다." },
  failed: { label: "실패", tone: "error", hint: "생성 작업이 실패했습니다 — 정리 대상입니다." },
  expired: { label: "만료", tone: "neutral", hint: "보존 기간이 지나 만료됐습니다." },
  deleted: { label: "삭제됨", tone: "neutral", hint: "삭제 처리된 기록입니다." },
  orphan: { label: "미등록 객체", tone: "warn", hint: "저장소에만 존재하고 DB에 등록되지 않은 객체입니다 (RustFS 정합성 탭에서 정리)." }
};

export function lifecycleOf(value: string): LifecycleMeta {
  return lifecycleMeta[value] ?? { label: value, tone: "neutral", hint: value };
}
