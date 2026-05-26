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

export type LoadJobStatus = {
  job_id: string;
  kind: string;
  state: "queued" | "running" | "done" | "failed" | "cancelled";
  progress: number;
  current_stage?: string | null;
  error_message?: string | null;
  log_tail?: string[];
  payload_summary?: Record<string, unknown> | null;
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
  source_set: Record<string, string>;
  started_at: string;
  finished_at?: string | null;
  generated_by: "cli" | "api" | "cron";
};

export type ConsistencyReport = ConsistencyReportSummary & {
  cases: ConsistencyCase[];
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
  display_name?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
  job_id?: string | null;
  snapshot_id?: string | null;
  release_id?: string | null;
  created_at: string;
  finished_at?: string | null;
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
