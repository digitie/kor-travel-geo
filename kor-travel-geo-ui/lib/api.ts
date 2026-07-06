export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/proxy";
export const PUBLIC_API_KEY_STORAGE_KEY = "kortravelgeo.publicApiKey";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }

  /** message(=raw 응답 본문)가 JSON이면 파싱해 반환하고, 아니면 null. */
  get body(): unknown {
    try {
      return JSON.parse(this.message) as unknown;
    } catch {
      return null;
    }
  }

  /** 백엔드 관례인 `{"detail": ...}` 본문에서 detail만 추출한다 (없으면 null). */
  get detail(): unknown {
    const body = this.body;
    if (body && typeof body === "object" && "detail" in body) {
      return (body as { detail: unknown }).detail;
    }
    return null;
  }
}

/**
 * 오류를 사용자에게 보여줄 한 줄 문자열로 정리한다. ApiError는 raw JSON 본문 대신
 * detail/error/message 필드를 우선 노출한다.
 */
export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body;
    if (body && typeof body === "object") {
      const record = body as Record<string, unknown>;
      const candidate = record.detail ?? record.error ?? record.message;
      if (typeof candidate === "string" && candidate) return candidate;
      if (candidate != null) return JSON.stringify(candidate);
    }
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return String(error);
}

export function backendPath(path: string): string {
  const trimmed = path.startsWith("/") ? path : `/${path}`;
  return trimmed.startsWith("/v1") || trimmed.startsWith("/v2") ? trimmed : `/v1${trimmed}`;
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${backendPath(path)}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    // An expired/revoked session surfaces as 401 {"error":"AUTH_REQUIRED"} from the BFF proxy.
    // For an already-loaded SPA page, send the user to /login (preserving the return path)
    // instead of rendering the raw error string; guard against a redirect loop on /login itself.
    if (
      response.status === 401 &&
      typeof window !== "undefined" &&
      window.location.pathname !== "/login"
    ) {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.assign(`/login?next=${next}`);
    }
    const text = await response.text();
    throw new ApiError(response.status, text || `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    body: JSON.stringify(body)
  });
}

export async function postPublicJson<T>(
  path: string,
  body: unknown,
  fallbackApiKey = ""
): Promise<T> {
  return postJson<T>(pathWithPublicApiKey(path, fallbackApiKey), body);
}

export async function patchJson<T>(path: string, body: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
}

export async function deleteJson<T>(path: string): Promise<T> {
  return requestJson<T>(path, { method: "DELETE" });
}

export function savePublicApiKeyForRequests(apiKey: string): void {
  if (typeof window === "undefined") return;
  const trimmed = apiKey.trim();
  if (trimmed) {
    window.localStorage.setItem(PUBLIC_API_KEY_STORAGE_KEY, trimmed);
  }
}

export function clearPublicApiKeyForRequestsByHint(keyHint: string): void {
  if (typeof window === "undefined") return;
  const current = window.localStorage.getItem(PUBLIC_API_KEY_STORAGE_KEY)?.trim();
  if (current?.endsWith(keyHint)) {
    window.localStorage.removeItem(PUBLIC_API_KEY_STORAGE_KEY);
  }
}

function pathWithPublicApiKey(path: string, fallbackApiKey: string): string {
  const apiKey = publicApiKeyForRequests() || fallbackApiKey.trim();
  if (!apiKey) {
    return path;
  }
  const [pathname, search = ""] = path.split("?", 2);
  const params = new URLSearchParams(search);
  params.set("key", apiKey);
  const query = params.toString();
  return query ? `${pathname}?${query}` : pathname;
}

function publicApiKeyForRequests(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(PUBLIC_API_KEY_STORAGE_KEY)?.trim() ?? "";
}

export type LoadJobStatus = {
  job_id: string;
  kind: string;
  state: "queued" | "running" | "done" | "failed" | "cancelled";
  load_batch_id?: string | null;
  parent_job_id?: string | null;
  progress: number;
  current_stage?: string | null;
  source_yyyymm?: string | null;
  source_set?: Record<string, unknown> | null;
  started_at?: string | null;
  finished_at?: string | null;
  heartbeat_at?: string | null;
  error_message?: string | null;
  log_tail?: string[];
  payload_summary?: Record<string, unknown> | null;
};

export type SourceKind =
  | "juso"
  | "parcel_link"
  | "locsum"
  | "navi"
  | "shp"
  | "roadaddr_entrance"
  | "sppn_makarea"
  | "pobox"
  | "bulk";

export type UploadStorageKind = "local" | "rustfs";

// SourceCandidate / SourceSetDiscovery / SourceSetPlan types were removed in
// T-201 along with the legacy auto-detection upload-SET surface. Explicit
// category selection lives in the T-209 /admin/source-files UI.

export type UploadFileStatus = {
  upload_set_id: string;
  file_id: string;
  filename: string;
  relative_path?: string | null;
  path: string;
  state: "pending" | "uploading" | "uploaded" | "cancelled" | "failed";
  storage_kind: UploadStorageKind;
  storage_uri?: string | null;
  object_key?: string | null;
  object_etag?: string | null;
  size_bytes: number;
  uploaded_bytes: number;
  sha256?: string | null;
  inferred_yyyymm?: string | null;
  source_kind?: SourceKind | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
};

export type UploadSetStatus = {
  upload_set_id: string;
  purpose: string;
  state: "created" | "uploading" | "uploaded" | "cancelled" | "failed";
  root_path: string;
  storage_kind: UploadStorageKind;
  storage_uri?: string | null;
  storage_prefix?: string | null;
  materialized_path?: string | null;
  files: UploadFileStatus[];
  total_bytes: number;
  uploaded_bytes: number;
  created_at: string;
  updated_at: string;
  error_message?: string | null;
};

export type RustfsSecretStatus = {
  configured: boolean;
  hint?: string | null;
};

export type RustfsStorageConfig = {
  enabled: boolean;
  endpoint_url: string;
  bucket: string;
  prefix: string;
  region: string;
  force_path_style: boolean;
  retention_days: number;
  access_key: RustfsSecretStatus;
  secret_key: RustfsSecretStatus;
};

export type RustfsStorageConfigPatch = Partial<{
  enabled: boolean;
  endpoint_url: string;
  bucket: string;
  prefix: string;
  region: string;
  force_path_style: boolean;
  retention_days: number;
  access_key: string;
  secret_key: string;
}>;

export type RustfsConnectionCheck = {
  ok: boolean;
  endpoint_url: string;
  bucket: string;
  prefix: string;
  message?: string | null;
};

export type PublicApiKeySummary = {
  public_api_key_id: string;
  label?: string | null;
  key_hint: string;
  state: "active" | "revoked";
  created_at: string;
  created_by?: string | null;
  revoked_at?: string | null;
  revoked_by?: string | null;
};

export type PublicApiKeyCreateResponse = {
  key: string;
  item: PublicApiKeySummary;
};

export type RustfsSyncLocalResult = {
  upload_set: UploadSetStatus;
  uploaded_files: number;
  uploaded_bytes: number;
  skipped_files: number;
};

export type TableStat = {
  table_name: string;
  row_count: number;
  size_bytes?: number | null;
  updated_at?: string | null;
};

export type CacheMetrics = {
  enabled: boolean;
  entries: number;
  hits: number;
  expired: number;
};

export type ConsistencyCase = {
  code: string;
  name: string;
  severity: "OK" | "INFO" | "WARN" | "ERROR";
  count: number;
  ratio?: number | null;
  threshold?: string | null;
  metric?: Record<string, number> | null;
  sample?: Record<string, unknown>[];
  note?: string | null;
};

export type ConsistencyReportSummary = {
  report_id: string;
  scope: string;
  severity_max: "OK" | "INFO" | "WARN" | "ERROR";
  source_set: Record<string, unknown>;
  started_at: string;
  finished_at?: string | null;
  generated_by: "cli" | "api" | "cron";
};

export type ConsistencyReport = ConsistencyReportSummary & {
  cases: ConsistencyCase[];
};

export type ConsistencyDecisionState = "unreviewed" | "approved" | "rejected" | "deferred";

export type ConsistencyCaseDefinition = {
  code: string;
  name: string;
  compares: string;
  abnormal_criteria: string;
  evidence: string[];
  likely_causes: string[];
  decision_guide: string;
  // T-226: align hand-rolled type with the backend contract (api.gen ConsistencyCaseDefinition).
  default_severity?: "OK" | "INFO" | "WARN" | "ERROR" | null;
  sample_schema?: Record<string, unknown> | null;
  threshold?: string | null;
};

export type ConsistencySamplePoint = {
  x: number;
  y: number;
};

export type ConsistencyCaseSample = {
  sample_id: string;
  report_id: string;
  case_code: string;
  severity: "OK" | "INFO" | "WARN" | "ERROR";
  sample_rank: number;
  bd_mgt_sn?: string | null;
  rncode_full?: string | null;
  sig_cd?: string | null;
  bjd_cd?: string | null;
  distance_m?: number | null;
  source_yyyymm?: string | null;
  source_kind?: string | null;
  case_metric: Record<string, unknown>;
  source_snapshot: Record<string, unknown>;
  point?: ConsistencySamplePoint | null;
  bbox_4326: Record<string, unknown>;
  has_polygon: boolean;
  has_line: boolean;
  decision_state: ConsistencyDecisionState;
  reason_code?: string | null;
  note?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  created_at: string;
};

export type ConsistencySamplePage = {
  report_id: string;
  case_code: string;
  total: number;
  page: number;
  page_size: number;
  items: ConsistencyCaseSample[];
};

export type ConsistencyCaseSummary = {
  report_id: string;
  case_code: string;
  total: number;
  by_severity: Record<string, number>;
  by_decision: Record<string, number>;
  by_sig_cd: Record<string, number>;
  distance: Record<string, number>;
};

export type ConsistencySampleDecisionRequest = {
  decision_state: Exclude<ConsistencyDecisionState, "unreviewed">;
  reason_code: string;
  note?: string | null;
  reviewer?: string | null;
};

export type ConsistencyBulkDecisionRequest = ConsistencySampleDecisionRequest & {
  sample_ids: string[];
};

export type ConsistencyBulkDecisionResponse = {
  report_id: string;
  case_code: string;
  updated_count: number;
  items: ConsistencyCaseSample[];
};

export type ConsistencySampleRecheckResponse = {
  sample_id: string;
  report_id: string;
  case_code: string;
  exists_in_current_mv: boolean;
  point?: ConsistencySamplePoint | null;
  stale: boolean;
  evidence: Record<string, unknown>;
};

export type AuditEvent = {
  audit_event_id: string;
  occurred_at: string;
  actor_type: "system" | "cli" | "api" | "ui" | "scheduler";
  actor_id?: string | null;
  action: string;
  outcome: "started" | "succeeded" | "failed" | "cancelled" | "denied";
  resource_type?: string | null;
  resource_id?: string | null;
  job_id?: string | null;
  error_code?: string | null;
  payload_redacted?: Record<string, unknown>;
  client_ip_hash?: string | null;
  user_agent_hash?: string | null;
};

export type DatasetSnapshot = {
  dataset_snapshot_id: string;
  state: "building" | "validated" | "rejected" | "released" | "retired";
  source_set: Record<string, unknown>;
  source_set_hash: string;
  row_counts: Record<string, number>;
  consistency_report_id?: string | null;
  created_by_job_id?: string | null;
  created_at: string;
  validated_at?: string | null;
};

export type ServingRelease = {
  serving_release_id: string;
  dataset_snapshot_id: string;
  state: "pending" | "active" | "superseded" | "rolled_back" | "failed";
  release_kind: "full_load" | "daily_delta" | "restore" | "manual_rebuild" | "rollback";
  mv_name: string;
  activated_by_job_id?: string | null;
  activated_at?: string | null;
  created_at: string;
};

export type OpsArtifact = {
  artifact_id: string;
  artifact_type: string;
  state: "creating" | "available" | "failed" | "deleted" | "expired";
  storage_kind: "local_file" | "s3" | "gcs" | "none";
  storage_uri?: string | null;
  display_name?: string | null;
  media_type?: string | null;
  compression?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
  retention_class?: string | null;
  expires_at?: string | null;
  job_id?: string | null;
  dataset_snapshot_id?: string | null;
  serving_release_id?: string | null;
  manifest?: Record<string, unknown>;
  callback_url?: string | null;
  callback_state?: string | null;
  created_at: string;
  finished_at?: string | null;
};

export type BackupArtifact = OpsArtifact & {
  artifact_type: "db_backup";
  download_url?: string | null;
  // T-240 manifest-derived catalog summary (null for legacy/skipped manifests).
  source_set_yyyymm?: Record<string, string | null> | null;
  source_set_mixed?: boolean | null;
  source_inventory_ok?: boolean | null;
};

export type BackupAllowedDirs = {
  dirs: string[];
  default_dir?: string | null;
};

export type RestoreDryRunResult = {
  can_restore: boolean;
  mode: "new_database" | "replace_current";
  target_database?: string | null;
  blockers?: string[];
  warnings?: string[];
  archive_sha256_ok?: boolean | null;
  internal_checksums_ok?: boolean | null;
  manifest_ok?: boolean | null;
  backup_postgres_version?: string | null;
  backup_postgis_version?: string | null;
  target_postgres_version?: string | null;
  target_postgis_version?: string | null;
  row_counts?: Record<string, number> | null;
};

export type RestoreHotSwapPlan = {
  current_database: string;
  restore_database: string;
  previous_alias: string;
  maintenance_database: string;
  typed_confirmation: string;
  rollback_confirmation: string;
  previous_alias_retention_days: number;
  can_execute: boolean;
  blockers?: string[];
  steps?: string[];
  sql?: string[];
};

export type RestoreHotSwapResult = {
  swapped: boolean;
  current_database: string;
  restore_database: string;
  previous_alias: string;
  rolled_back?: boolean;
  smoke_ok?: boolean | null;
  serving_release_id?: string | null;
  previous_release_id?: string | null;
  rollback_confirmation?: string | null;
  message?: string | null;
};

export type RestoreHotSwapRollbackResult = {
  rolled_back: boolean;
  current_database: string;
  restore_database: string;
  previous_alias: string;
  smoke_ok?: boolean | null;
  serving_release_id?: string | null;
  previous_release_id?: string | null;
  blockers?: string[];
  message?: string | null;
};

export type RestoreRowCountDiff = {
  object: string;
  expected?: number | null;
  actual: number;
  match: boolean;
};

export type RestoreReconcileResult = {
  ok: boolean;
  target_database?: string | null;
  row_count_diffs?: RestoreRowCountDiff[];
  mv_geocode_target_rows?: number | null;
  mv_geocode_text_search_rows?: number | null;
  mv_nonempty_ok?: boolean | null;
  sppn_rows?: number | null;
  pt_source_distribution?: Record<string, number> | null;
  source_set_yyyymm?: Record<string, string | null> | null;
  warnings?: string[];
};

export type RestoreSourceVerificationResult = {
  entrypoint: "pg_restore" | "rename_hot_swap";
  run_quick_reconcile: boolean;
  legacy_estimate_only?: boolean;
  active_source_match_set_id?: string | null;
  reconcile_run_id?: string | null;
  mismatch_count: number;
  reconstruct_unavailable: boolean;
  message?: string | null;
};

export type MaintenanceWindow = {
  maintenance_window_id: string;
  kind: "full_load" | "restore" | "schema_migration" | "mv_refresh" | "read_only" | "exclusive";
  state: "scheduled" | "active" | "ending" | "ended" | "cancelled" | "failed";
  starts_at?: string | null;
  ends_at?: string | null;
  actual_started_at?: string | null;
  actual_ended_at?: string | null;
  reason: string;
  requested_by?: string | null;
  approved_by?: string | null;
  blocks?: Record<string, unknown>;
  created_at: string;
};

export type TableStatsSnapshot = {
  table_stats_snapshot_id: string;
  dataset_snapshot_id?: string | null;
  captured_at: string;
  schema_name: string;
  object_name: string;
  object_kind: "table" | "materialized_view" | "index" | "toast" | "other";
  estimated_rows?: number | null;
  exact_rows?: number | null;
  total_bytes?: number | null;
};

export type PgStatStatementSnapshot = {
  pg_stat_snapshot_id: string;
  captured_at: string;
  rank: number;
  queryid?: string | null;
  query_fingerprint: string;
  operation: string;
  calls: number;
  total_exec_time_ms: number;
  mean_exec_time_ms: number;
  max_exec_time_ms: number;
  rows_returned: number;
  shared_blks_hit: number;
  shared_blks_read: number;
  temp_blks_read: number;
  temp_blks_written: number;
  query_preview: string;
  stats?: Record<string, unknown>;
};
