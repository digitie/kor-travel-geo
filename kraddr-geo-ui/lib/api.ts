export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/proxy";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function backendPath(path: string): string {
  const trimmed = path.startsWith("/") ? path : `/${path}`;
  return trimmed.startsWith("/v1") ? trimmed : `/v1${trimmed}`;
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

export async function patchJson<T>(path: string, body: unknown): Promise<T> {
  return requestJson<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
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

export type SourceCandidate = {
  kind: SourceKind;
  path: string;
  inferred_yyyymm?: string | null;
  sido_count?: number | null;
  file_count?: number | null;
  byte_size?: number | null;
  sha256?: string | null;
  confidence: "high" | "medium" | "low";
  note?: string | null;
};

export type SourceSetDiscovery = {
  root_path: string;
  candidates: SourceCandidate[];
  recommended: Partial<Record<SourceKind, SourceCandidate>>;
  missing_required: string[];
  mixed_yyyymm: boolean;
  yyyymm_by_kind: Partial<Record<SourceKind, string | null>>;
  warning?: string | null;
};

export type SourceSetPlan = {
  source_set_id: string;
  root_path?: string | null;
  candidates: SourceCandidate[];
  selected: Partial<Record<SourceKind, SourceCandidate>>;
  missing_required: string[];
  yyyymm_by_kind: Partial<Record<SourceKind, string | null>>;
  mixed_yyyymm: boolean;
  mixed_yyyymm_acknowledged: boolean;
  acknowledged_by?: "cli" | "api" | "ui" | null;
  acknowledged_at?: string | null;
  confirmation_token_hash?: string | null;
  expected_confirmation_token?: string | null;
  candidate_paths: Record<string, string>;
  candidate_sha256: Record<string, string | null>;
  batch_payload: Record<string, unknown>;
  warning?: string | null;
};

export type UploadFileStatus = {
  upload_set_id: string;
  file_id: string;
  filename: string;
  relative_path?: string | null;
  path: string;
  state: "pending" | "uploading" | "uploaded" | "cancelled" | "failed";
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
  files: UploadFileStatus[];
  total_bytes: number;
  uploaded_bytes: number;
  created_at: string;
  updated_at: string;
  error_message?: string | null;
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
  event_id: string;
  occurred_at: string;
  actor_type: "system" | "cli" | "api" | "ui" | "scheduler";
  action: string;
  outcome: "started" | "succeeded" | "failed" | "cancelled" | "denied";
  resource_type?: string | null;
  resource_id?: string | null;
  job_id?: string | null;
  payload_redacted?: Record<string, unknown>;
};

export type DatasetSnapshot = {
  snapshot_id: string;
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
  release_id: string;
  snapshot_id: string;
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
  snapshot_id?: string | null;
  release_id?: string | null;
  manifest?: Record<string, unknown>;
  callback_url?: string | null;
  callback_state?: string | null;
  created_at: string;
  finished_at?: string | null;
};

export type BackupArtifact = OpsArtifact & {
  artifact_type: "db_backup";
  download_url?: string | null;
};

export type MaintenanceWindow = {
  window_id: string;
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
  stats_id: string;
  snapshot_id?: string | null;
  captured_at: string;
  schema_name: string;
  object_name: string;
  object_kind: "table" | "materialized_view" | "index" | "toast" | "other";
  estimated_rows?: number | null;
  exact_rows?: number | null;
  total_bytes?: number | null;
};
