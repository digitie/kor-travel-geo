import type { components } from "@/types/api.gen";

// --- Generated-type aliases (single source of truth: types/api.gen.ts) -------

export type SourceFileCategoryInfo = components["schemas"]["SourceFileCategoryInfo"];
export type SourceFileCategoryCatalog = components["schemas"]["SourceFileCategoryCatalog"];
export type SourceCategory = SourceFileCategoryInfo["category"];
export type SourceRole = SourceFileCategoryInfo["role"];
export type SourceGroupKind = SourceFileCategoryInfo["group_kind"];

export type UploadSessionStatus = components["schemas"]["UploadSessionStatus"];
export type UploadSessionFileSlot = components["schemas"]["UploadSessionFileSlot"];
export type UploadSessionCreateRequest = components["schemas"]["UploadSessionCreateRequest"];
export type UploadSessionState = UploadSessionStatus["state"];
export type MultipartInitiateResponse = components["schemas"]["MultipartInitiateResponse"];
export type MultipartCompleteRequest = components["schemas"]["MultipartCompleteRequest"];
export type UploadPartResponse = components["schemas"]["UploadPartResponse"];

export type SourceMatchSet = components["schemas"]["SourceMatchSet"];
export type SourceMatchSetDetail = components["schemas"]["SourceMatchSetDetail"];
export type SourceMatchSetItem = components["schemas"]["SourceMatchSetItem"];
export type SourceMatchSetState = SourceMatchSet["state"];
export type SourceMatchSetValidateResponse = components["schemas"]["SourceMatchSetValidateResponse"];
export type SourceMatchSetActivateResponse = components["schemas"]["SourceMatchSetActivateResponse"];
export type SourceMatchSetRetireResponse = components["schemas"]["SourceMatchSetRetireResponse"];
export type SourceRebuildDbRequest = components["schemas"]["SourceRebuildDbRequest"];
export type SourceRebuildDbResponse = components["schemas"]["SourceRebuildDbResponse"];

export type SourceGroupSoftDeleteResponse = components["schemas"]["SourceGroupSoftDeleteResponse"];
export type SourceGroupRestoreResponse = components["schemas"]["SourceGroupRestoreResponse"];
export type SourceGroupRelinkResponse = components["schemas"]["SourceGroupRelinkResponse"];

export type SourceReconcileRun = components["schemas"]["SourceReconcileRun"];
export type SourceReconcileItem = components["schemas"]["SourceReconcileItem"];
export type SourceReconcileItemPage = components["schemas"]["SourceReconcileItemPage"];
export type ReconcileRunRequest = components["schemas"]["ReconcileRunRequest"];
export type ReconcileResolveRequest = components["schemas"]["ReconcileResolveRequest"];
export type ReconcileResolveResponse = components["schemas"]["ReconcileResolveResponse"];
export type ReconcileIssueType = SourceReconcileItem["issue_type"];
export type ReconcileResolveAction = ReconcileResolveRequest["action"];

export type SourceCapacityUsage = components["schemas"]["SourceCapacityUsage"];
export type SourceCategoryCapacity = components["schemas"]["SourceCategoryCapacity"];

export type ConsistencyReportSummary = components["schemas"]["ConsistencyReportSummary"];
export type ConsistencyReport = components["schemas"]["ConsistencyReport"];
export type ConsistencyCaseDefinition = components["schemas"]["ConsistencyCaseDefinition"];

export type ServingRelease = components["schemas"]["ServingRelease"];
export type DatasetSnapshot = components["schemas"]["DatasetSnapshot"];

// --- Labels (Korean) ---------------------------------------------------------

export const sourceRoleLabels: Record<SourceRole, string> = {
  build_required: "필수 구성",
  build_recommended: "권장 구성",
  validation_optional: "검증 선택",
  enrichment_candidate: "보강 후보"
};

export const matchSetStateLabels: Record<SourceMatchSetState, string> = {
  draft: "초안",
  validated: "검증 완료",
  active: "활성",
  retired: "은퇴",
  invalid: "무효",
  revalidatable: "재검증 가능",
  restored_from_backup: "백업 복원"
};

// 12 reconcile issue types (doc lines ~662-704).
export const reconcileIssueLabels: Record<ReconcileIssueType, string> = {
  db_missing_object: "DB row 있으나 객체 없음",
  object_missing_db: "객체 있으나 DB row 없음",
  pending_registration: "등록 대기",
  registration_expired: "등록 기한 만료",
  source_file_unavailable: "원천 파일 사용 불가",
  source_file_group_incomplete: "그룹 미완성",
  size_mismatch: "크기 불일치",
  hash_mismatch: "해시 불일치",
  etag_mismatch: "ETag 불일치",
  duplicate_object: "중복 객체",
  orphaned_multipart: "고아 multipart",
  delete_failed: "삭제 실패"
};

// epost categories use the manual server-fetch flow (T-207), not browser upload.
export const epostCategories: ReadonlySet<SourceCategory> = new Set<SourceCategory>([
  "epost_pobox_full",
  "epost_bulk_full"
]);

export function isEpostCategory(category: SourceCategory): boolean {
  return epostCategories.has(category);
}

// Non-terminal upload-session states are the resumable ones (doc line ~1296).
const TERMINAL_UPLOAD_STATES: ReadonlySet<UploadSessionState> = new Set<UploadSessionState>([
  "registered",
  "available",
  "cancelled",
  "expired",
  "registration_expired"
]);

export function isResumableSession(session: UploadSessionStatus): boolean {
  return !TERMINAL_UPLOAD_STATES.has(session.state);
}

export function isFailedSessionState(state: UploadSessionState): boolean {
  return state.startsWith("failed_");
}

export function shortHash(hash?: string | null, length = 12): string {
  if (!hash) return "-";
  return hash.length <= length ? hash : `${hash.slice(0, length)}…`;
}

// --- Path builders -----------------------------------------------------------

export const sourceFilesPaths = {
  categories: () => "/admin/source-file-categories",
  capacity: () => "/admin/source-files/capacity",
  uploadSessions: () => "/admin/source-files/upload-sessions",
  uploadSessionsList: (query?: { state?: string; category?: string; user_yyyymm?: string }) => {
    const params = new URLSearchParams();
    if (query?.state) params.set("state", query.state);
    if (query?.category) params.set("category", query.category);
    if (query?.user_yyyymm) params.set("user_yyyymm", query.user_yyyymm);
    const search = params.toString();
    return `/admin/source-files/upload-sessions${search ? `?${search}` : ""}`;
  },
  uploadSession: (id: string) => `/admin/source-files/upload-sessions/${id}`,
  registerSession: (id: string) => `/admin/source-files/upload-sessions/${id}/register`,
  matchSets: (state?: string) =>
    `/admin/source-match-sets${state ? `?state=${encodeURIComponent(state)}` : ""}`,
  matchSet: (id: string) => `/admin/source-match-sets/${id}`,
  matchSetValidate: (id: string) => `/admin/source-match-sets/${id}/validate`,
  matchSetActivate: (id: string) => `/admin/source-match-sets/${id}/activate`,
  matchSetRetire: (id: string) => `/admin/source-match-sets/${id}/retire`,
  matchSetRebuildDb: (id: string) => `/admin/source-match-sets/${id}/rebuild-db`,
  matchSetRunValidation: (id: string) => `/admin/source-match-sets/${id}/run-validation`,
  group: (id: string) => `/admin/source-file-groups/${id}`,
  groupSoftDelete: (id: string) => `/admin/source-file-groups/${id}/soft-delete`,
  groupRestore: (id: string) => `/admin/source-file-groups/${id}/restore`,
  groupRelink: (id: string) => `/admin/source-file-groups/${id}/relink`,
  groupValidate: (id: string) => `/admin/source-file-groups/${id}/validate`,
  reconcile: () => "/admin/source-files/reconcile",
  reconcileList: (limit = 20) => `/admin/source-files/reconcile?limit=${limit}`,
  reconcileRun: (id: string) => `/admin/source-files/reconcile/${id}`,
  reconcileItems: (id: string, query?: { issue_type?: string; state?: string }) => {
    const params = new URLSearchParams();
    if (query?.issue_type) params.set("issue_type", query.issue_type);
    if (query?.state) params.set("state", query.state);
    const search = params.toString();
    return `/admin/source-files/reconcile/${id}/items${search ? `?${search}` : ""}`;
  },
  reconcileItemResolve: (itemId: string) =>
    `/admin/source-files/reconcile/items/${itemId}/resolve`,
  consistency: () => "/admin/consistency",
  consistencyReport: (id: string) => `/admin/consistency/${id}`,
  consistencyCaseDefinitions: () => "/admin/consistency/case-definitions",
  servingReleases: (limit = 5) => `/admin/ops/releases?limit=${limit}`,
  snapshots: (limit = 10) => `/admin/ops/snapshots?limit=${limit}`
};

/**
 * The rebuild-db forced-promotion confirmation phrase (doc ~1559, ADR-049 #13).
 * A forced promotion requires the operator to type ``REBUILD-PROMOTE {id}`` exactly.
 */
export function rebuildPromoteConfirmation(matchSetId: string): string {
  return `REBUILD-PROMOTE ${matchSetId}`;
}

export function suggestYyyymm(now: Date = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  return `${year}${month}`;
}

export function isValidYyyymm(value: string): boolean {
  return /^\d{6}$/.test(value);
}
