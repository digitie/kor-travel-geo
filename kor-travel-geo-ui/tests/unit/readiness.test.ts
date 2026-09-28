import { describe, expect, it } from "vitest";

import { servingRelationIssues, type ReadinessResponse } from "@/lib/readiness";

function readiness(serving?: ReadinessResponse["components"][string]): ReadinessResponse {
  return {
    status: serving?.status === "degraded" ? "degraded" : "ok",
    ready: true,
    degraded: serving?.status === "degraded",
    components: {
      database: { status: "ok" },
      pool: { status: "ok" },
      ...(serving ? { serving } : {})
    }
  };
}

describe("servingRelationIssues (T-309)", () => {
  it("degraded serving component에서 ok가 아닌 MV와 상태를 한국어로 뽑는다", () => {
    const issues = servingRelationIssues(
      readiness({
        status: "degraded",
        detail: {
          relations: {
            mv_geocode_target: "empty",
            mv_geocode_text_search: "not_populated"
          }
        }
      })
    );

    expect(issues).toEqual(["mv_geocode_target 비어 있음", "mv_geocode_text_search populate 안 됨"]);
  });

  it("ok인 MV는 빼고 missing은 '없음'으로 표시한다", () => {
    const issues = servingRelationIssues(
      readiness({
        status: "degraded",
        detail: { relations: { mv_geocode_target: "ok", mv_geocode_text_search: "missing" } }
      })
    );

    expect(issues).toEqual(["mv_geocode_text_search 없음"]);
  });

  it("serving을 확인하지 못했으면(unknown/skipped/구버전) 경고하지 않는다", () => {
    expect(servingRelationIssues(readiness({ status: "unknown", error_type: "TimeoutError" }))).toEqual([]);
    expect(servingRelationIssues(readiness({ status: "skipped" }))).toEqual([]);
    expect(servingRelationIssues(readiness())).toEqual([]);
    expect(servingRelationIssues(null)).toEqual([]);
  });
});
