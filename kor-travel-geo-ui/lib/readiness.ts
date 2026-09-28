import type { components } from "@/types/api.gen";

export type ReadinessResponse = components["schemas"]["ReadinessResponse"];

const SERVING_STATE_LABELS: Record<string, string> = {
  empty: "비어 있음",
  not_populated: "populate 안 됨",
  missing: "없음"
};

/**
 * `/v1/readyz`의 `components.serving`에서 ok가 아닌 서빙 MV를 `이름 상태` 문자열로 뽑는다.
 * serving 확인이 안 됐으면(unknown/skipped/serving component가 없는 구버전 API) 빈 배열이다 —
 * 확인하지 못한 것을 비었다고 경고하지 않는다.
 */
export function servingRelationIssues(readiness: ReadinessResponse | null | undefined): string[] {
  const serving = readiness?.components?.serving;
  if (!serving || serving.status !== "degraded") return [];
  const relations = serving.detail?.relations;
  if (!relations || typeof relations !== "object") return [];
  return Object.entries(relations as Record<string, unknown>)
    .filter(([, state]) => state !== "ok")
    .map(([name, state]) => `${name} ${SERVING_STATE_LABELS[String(state)] ?? String(state)}`);
}
