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
