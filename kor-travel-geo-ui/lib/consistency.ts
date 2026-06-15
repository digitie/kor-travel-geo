const severityOrder = { OK: 0, INFO: 1, WARN: 2, ERROR: 3 } as const;

export function severityClass(value: string): "ok" | "warn" | "error" {
  if (typeof value !== "string") return "ok";
  const normalized = value.toUpperCase();
  if (normalized === "ERROR" || normalized === "FAILED") return "error";
  if (normalized === "WARN" || normalized === "CANCELLED") return "warn";
  return "ok";
}

export function severityRank(value: keyof typeof severityOrder): number {
  return severityOrder[value];
}

export const decisionLabels = {
  unreviewed: "미검토",
  approved: "승인",
  rejected: "거절",
  deferred: "보류"
} as const;

export const decisionReasons = {
  approved: [
    "source_gap",
    "known_boundary_issue",
    "mixed_yyyymm_acknowledged",
    "legacy_source",
    "manual_verified"
  ],
  rejected: [
    "loader_key_error",
    "coordinate_error",
    "source_set_error",
    "parser_error",
    "upstream_data_error",
    "needs_code_fix"
  ],
  deferred: ["needs_source_file_check", "needs_map_check", "needs_reload", "needs_policy_decision"]
} as const;

export function consistencySamplesPath({
  reportId,
  caseCode,
  severity,
  decision,
  sigCd,
  orderBy,
  desc,
  page,
  pageSize,
  format
}: {
  reportId: string;
  caseCode: string;
  severity?: string;
  decision?: string;
  sigCd?: string;
  orderBy?: string;
  desc?: boolean;
  page?: number;
  pageSize?: number;
  format?: "json" | "csv";
}): string {
  const params = new URLSearchParams();
  if (severity) params.set("severity", severity);
  if (decision) params.set("decision", decision);
  if (sigCd) params.set("sig_cd", sigCd);
  if (orderBy) params.set("order_by", orderBy);
  if (desc) params.set("desc", "true");
  if (page) params.set("page", String(page));
  if (pageSize) params.set("page_size", String(pageSize));
  if (format && format !== "json") params.set("format", format);
  const query = params.toString();
  return `/admin/consistency/${reportId}/cases/${caseCode}/samples${query ? `?${query}` : ""}`;
}
