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
export type EpostServerFetchRequest = components["schemas"]["EpostServerFetchRequest"];
export type EpostServerFetchResponse = components["schemas"]["EpostServerFetchResponse"];

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
export type SourceRetentionRecommendation =
  components["schemas"]["SourceRetentionRecommendation"];

export type SourceBulkHardDeleteRequest = components["schemas"]["SourceBulkHardDeleteRequest"];
export type SourceBulkHardDeleteResponse = components["schemas"]["SourceBulkHardDeleteResponse"];
export type SourceHardDeleteOutcome = components["schemas"]["SourceHardDeleteOutcome"];

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

/** Safe label for a match-set item role (falls back to the raw value). */
export function sourceRoleLabel(role: string): string {
  return (sourceRoleLabels as Record<string, string>)[role] ?? role;
}

// --- Serving-usage classification (T-220 audit / T-221, ADR-054) -------------
// Distinct from `role`: tells the operator how a source relates to ACTIVE serving
// coordinates, so a validation-only / no-go optional source is never rendered as
// "활용 중". `role`/`default_role` are build/match-set hints only.

export type SourceServingUsage = SourceFileCategoryInfo["serving_usage"];

export const servingUsageLabels: Record<SourceServingUsage, string> = {
  serving_core: "활용 중(서빙)",
  validation_only: "검증 전용",
  typed_feature_candidate: "상세주소 기능 후보",
  separate_feature_candidate: "별도 기능 후보(서빙 미반영)",
  promotion_blocked_no_go: "승격 보류(no-go)"
};

/** Badge colour per serving-usage: green only for active serving core. */
export const servingUsageTones: Record<SourceServingUsage, "ok" | "warn" | "error"> = {
  serving_core: "ok",
  validation_only: "warn",
  typed_feature_candidate: "warn",
  separate_feature_candidate: "warn",
  promotion_blocked_no_go: "error"
};

const servingUsageGenericNotes: Record<SourceServingUsage, string> = {
  serving_core: "현재 active serving 좌표/텍스트 정본으로 사용 중.",
  validation_only: "검증·overlay 전용 — active serving 좌표 원천이 아님.",
  typed_feature_candidate:
    "상세주소 typed feature 후보 — 호별 좌표 없음, 일반 주소 대표 좌표 원천 아님.",
  separate_feature_candidate:
    "별도 기능(POI/우편) 후보 — active serving 좌표에 반영되지 않음.",
  promotion_blocked_no_go: "대표좌표 승격을 평가했으나 보류(no-go) — 검증·분석용으로만 유지."
};

// Per-category ADR-054 boundary notes (override the generic serving-usage note).
const servingUsageCategoryNotes: Partial<Record<SourceCategory, string>> = {
  roadaddr_building_shape_bundle:
    "C11 출입구 후보: T-125 검증 결과 no-go(대표점 대비 p95 22.8m·100m 초과 14,433건·C4/C6/C7 악화)로 대표좌표 승격 보류.",
  national_point_grid_shape:
    "국가지점번호 serving 좌표는 core.sppn 10m 계산값 — 이 grid 파일은 검증·overlay 전용(좌표 원천 아님).",
  national_point_grid_center:
    "국가지점번호 serving 좌표는 core.sppn 10m 계산값 — 이 중심점 파일은 검증 전용(좌표 원천 아님).",
  civil_service_institution_map:
    "POI 원천 — 주소 대표 좌표를 대체하지 않음(별도 장소 검색 후보).",
  address_db_full: "C16 key/row drift 검증 전용 — 좌표·정본 대체 금지.",
  building_db_full: "C16 key/row drift 검증 전용 — 좌표·정본 대체 금지.",
  zone_shape_full:
    "TL_SPPN_MAKAREA는 국가지점번호 표기 의무지역 context — 좌표 원천 아님."
};

/** ADR-054 explanatory note for a category (per-category override → generic). */
export function servingUsageNote(category: SourceCategory, usage: SourceServingUsage): string {
  return servingUsageCategoryNotes[category] ?? servingUsageGenericNotes[usage];
}

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

/**
 * Fixed typed-confirmation phrase for the manual bulk hard-delete (T-212, ADR-052).
 * The operator must type this exactly; the backend requires `destructive_admin`
 * plus this phrase for `POST /v1/admin/source-files/bulk-hard-delete`.
 */
export const HARD_DELETE_CONFIRMATION = "HARD-DELETE-SOURCES";

/**
 * Reconcile issue types whose objects are cleanup-eligible ("정리 대상") for the
 * manual bulk hard-delete: unregistered stored objects. soft_deleted/quarantined
 * files are eligible too but surface in the 목록 tab, not as reconcile issues.
 * The backend re-validates eligibility and reports `skipped_ineligible` regardless,
 * so this only gates which rows offer a selection checkbox.
 */
const BULK_HARD_DELETE_ELIGIBLE_ISSUE_TYPES: ReadonlySet<ReconcileIssueType> =
  new Set<ReconcileIssueType>(["object_missing_db", "registration_expired"]);

export function isBulkHardDeleteEligible(item: SourceReconcileItem): boolean {
  return (
    item.state === "open" &&
    Boolean(item.object_key) &&
    BULK_HARD_DELETE_ELIGIBLE_ISSUE_TYPES.has(item.issue_type)
  );
}

// epost categories use the manual server-fetch flow (T-207), not browser upload.
const epostCategories: ReadonlySet<SourceCategory> = new Set<SourceCategory>([
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
  "registration_expired",
  "failed_upload",
  "failed_extract",
  "failed_structure",
  "failed_hash",
  "failed_rustfs_put",
  "failed_rustfs_verify",
  "failed_storage_state"
]);

export function isResumableSession(session: UploadSessionStatus): boolean {
  return !TERMINAL_UPLOAD_STATES.has(session.state);
}

export function isTerminalUploadState(state: UploadSessionState): boolean {
  return TERMINAL_UPLOAD_STATES.has(state);
}

export function isFailedSessionState(state: UploadSessionState): boolean {
  return state.startsWith("failed_");
}

/**
 * SSE `source_upload.progress` event payload (mirrors backend
 * `SourceUploadProgressEvent`). The events endpoint is a StreamingResponse with
 * no OpenAPI schema, so this is the hand-maintained client contract.
 */
export type SourceUploadProgressEvent = {
  event: "source_upload.progress";
  upload_session_id: string;
  state: UploadSessionState;
  stage?: string | null;
  progress?: number | null;
  current_item?: string | null;
  uploaded_bytes?: number;
  total_bytes?: number;
  message?: string | null;
  log_tail?: string | null;
};

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
  uploadSessionEvents: (id: string) =>
    `/admin/source-files/upload-sessions/${id}/events`,
  registerSession: (id: string) => `/admin/source-files/upload-sessions/${id}/register`,
  epostFetch: () => "/admin/source-files/epost-fetch",
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
  bulkHardDelete: () => "/admin/source-files/bulk-hard-delete",
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
