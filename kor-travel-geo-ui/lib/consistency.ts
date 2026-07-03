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

/**
 * 판정 사유 코드의 한국어 라벨 — 코드 값은 백엔드 enum 계약이므로 전송 값은
 * 그대로 두고 표시만 바꾼다.
 */
export const decisionReasonLabels: Record<string, string> = {
  source_gap: "원천 자료 누락 (정상 편차)",
  known_boundary_issue: "알려진 경계 이슈",
  mixed_yyyymm_acknowledged: "혼합 기준월 확인됨",
  legacy_source: "레거시 원천 특성",
  manual_verified: "수동 확인 완료",
  loader_key_error: "적재 키 오류",
  coordinate_error: "좌표 오류",
  source_set_error: "원천 구성 오류",
  parser_error: "파서 오류",
  upstream_data_error: "원천 데이터 오류",
  needs_code_fix: "코드 수정 필요",
  needs_source_file_check: "원천 파일 확인 필요",
  needs_map_check: "지도 확인 필요",
  needs_reload: "재적재 필요",
  needs_policy_decision: "정책 결정 필요"
};

export function decisionReasonLabel(code: string): string {
  const label = decisionReasonLabels[code];
  return label ? `${label} (${code})` : code;
}

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
