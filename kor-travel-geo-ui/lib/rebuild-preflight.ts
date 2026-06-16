import type { SourceMatchSetDetail } from "@/lib/source-files";

/**
 * T-226: pure pre-flight summary for the rebuild-db danger action. Aggregates the selected
 * match set's state into operator-facing checklist items so the UI can show "무엇이 준비됐고
 * 무엇이 막는가"를 enqueue 전에 보여 준다. Uses only the already-fetched SourceMatchSetDetail —
 * no backend changes. Mirrors (a subset of) the backend integrity/promotion gates for display;
 * the backend remains the authoritative gate.
 */

export type PreflightSeverity = "ok" | "warn" | "blocker";

export type PreflightItem = {
  key: string;
  label: string;
  severity: PreflightSeverity;
  detail: string;
};

export type RebuildPreflight = {
  items: PreflightItem[];
  affectedCategories: string[];
  blockerCount: number;
  warnCount: number;
  /** True when no blocker-severity item is present (display heuristic; backend is authoritative). */
  ready: boolean;
};

export function summarizeRebuildPreflight(detail: SourceMatchSetDetail): RebuildPreflight {
  const set = detail.match_set;
  const items = detail.items ?? [];
  const active = items.filter((it) => !it.omitted);
  const omitted = items.length - active.length;
  const withGroup = active.filter((it) => it.source_file_group_id).length;
  const missingGroup = active.filter((it) => !it.source_file_group_id);
  const requiredMissing = missingGroup.filter((it) => it.required);
  const affectedCategories = active.map((it) => it.category);

  const checks: PreflightItem[] = [];

  checks.push({
    key: "state",
    label: "매칭 세트 상태",
    severity: set.state === "active" || set.state === "validated" ? "ok" : "warn",
    detail: set.state
  });

  checks.push({
    key: "integrity",
    label: "무결성 경보",
    severity: set.integrity_alert ? "blocker" : "ok",
    detail: set.integrity_alert ? "integrity_alert 있음 — 해소 전 promotion 불가" : "없음"
  });

  checks.push({
    key: "groups",
    label: "원천 그룹 연결",
    severity: requiredMissing.length > 0 ? "blocker" : missingGroup.length > 0 ? "warn" : "ok",
    detail:
      requiredMissing.length > 0
        ? `필수 ${requiredMissing.length}개 카테고리 그룹 미연결`
        : missingGroup.length > 0
          ? `선택 ${missingGroup.length}개 미연결 (필수는 모두 연결)`
          : `${withGroup}/${active.length} 연결됨`
  });

  checks.push({
    key: "affected",
    label: "영향 카테고리",
    severity: active.length === 0 ? "blocker" : "ok",
    detail: active.length === 0 ? "포함 카테고리 없음" : `${active.length}개 (생략 ${omitted})`
  });

  const blockerCount = checks.filter((c) => c.severity === "blocker").length;
  const warnCount = checks.filter((c) => c.severity === "warn").length;

  return {
    items: checks,
    affectedCategories,
    blockerCount,
    warnCount,
    ready: blockerCount === 0
  };
}
