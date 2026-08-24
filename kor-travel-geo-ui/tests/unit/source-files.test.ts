import { describe, expect, it } from "vitest";
import {
  activeServingCategorySet,
  isEpostCategory,
  isFailedSessionState,
  isResumableSession,
  isValidYyyymm,
  MAX_LIVE_UPLOAD_STREAMS,
  rebuildPromoteConfirmation,
  selectLiveUploadStreamIds,
  reconcileIssueLabels,
  servingUsageLabels,
  servingUsageNote,
  servingUsageTones,
  shortHash,
  sourceFilesPaths,
  sourceRoleLabel,
  suggestYyyymm,
  type SourceServingUsage,
  type UploadSessionStatus
} from "@/lib/source-files";

function session(state: UploadSessionStatus["state"]): UploadSessionStatus {
  return {
    upload_session_id: "u1",
    category: "roadname_hangul_full",
    user_yyyymm: "202603",
    state,
    registration_state: "not_registered",
    group_kind: "single_file",
    uploaded_file_count: 0,
    expected_file_count: 1,
    max_bytes: 0,
    part_size_bytes: 0,
    file_slots: [],
    source_file_group_id: "g1",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    display_name: "x",
    storage_kind: "rustfs",
    upload_strategy: "multipart"
  } as unknown as UploadSessionStatus;
}

describe("serving-usage classification (T-221, ADR-054)", () => {
  const usages: SourceServingUsage[] = [
    "serving_core",
    "validation_only",
    "typed_feature_candidate",
    "separate_feature_candidate",
    "promotion_blocked_no_go"
  ];

  it("모든 serving_usage 값에 라벨과 톤이 있다", () => {
    for (const u of usages) {
      expect(servingUsageLabels[u]).toBeTruthy();
      expect(["ok", "warn", "error"]).toContain(servingUsageTones[u]);
    }
  });

  it("active serving core만 녹색(ok), no-go는 error 톤이다", () => {
    expect(servingUsageTones.serving_core).toBe("ok");
    expect(servingUsageTones.promotion_blocked_no_go).toBe("error");
    // validation/검증·별도 기능 후보는 녹색이 아니어야 한다(오해 방지).
    expect(servingUsageTones.validation_only).not.toBe("ok");
    expect(servingUsageTones.separate_feature_candidate).not.toBe("ok");
  });

  it("C11 카드 note는 T-125 no-go를, 국가지점번호는 계산값을 명시한다", () => {
    expect(servingUsageNote("roadaddr_building_shape_bundle", "promotion_blocked_no_go")).toContain(
      "no-go"
    );
    expect(servingUsageNote("national_point_grid_shape", "validation_only")).toContain("core.sppn");
    expect(servingUsageNote("civil_service_institution_map", "separate_feature_candidate")).toContain(
      "대체하지 않음"
    );
  });

  it("match-set item role을 한국어 라벨로 바꾸고 미지값은 원문 유지한다", () => {
    expect(sourceRoleLabel("validation_optional")).toBe("검증 선택");
    expect(sourceRoleLabel("build_required")).toBe("필수 구성");
    expect(sourceRoleLabel("omitted")).toBe("omitted");
  });

  it("active serving 카테고리 집합은 omitted 항목을 제외한다", () => {
    const items = [
      { category: "roadname_hangul_full", omitted: false },
      { category: "navi_full", omitted: false },
      { category: "national_point_grid_shape", omitted: true }
    ] as unknown as Parameters<typeof activeServingCategorySet>[0];
    const set = activeServingCategorySet(items);
    expect(set.has("roadname_hangul_full")).toBe(true);
    expect(set.has("navi_full")).toBe(true);
    expect(set.has("national_point_grid_shape")).toBe(false);
    expect(activeServingCategorySet([]).size).toBe(0);
  });
});

describe("source-files helpers", () => {
  it("non-terminal 세션만 재개 가능으로 판정한다", () => {
    expect(isResumableSession(session("uploading"))).toBe(true);
    expect(isResumableSession(session("created"))).toBe(true);
    expect(isResumableSession(session("registered"))).toBe(false);
    expect(isResumableSession(session("cancelled"))).toBe(false);
    expect(isResumableSession(session("registration_expired"))).toBe(false);
    expect(isResumableSession(session("failed_structure"))).toBe(false);
    expect(isResumableSession(session("failed_register"))).toBe(true);
  });

  it("failed_* 상태를 실패로 분류한다", () => {
    expect(isFailedSessionState("failed_upload")).toBe(true);
    expect(isFailedSessionState("failed_register")).toBe(true);
    expect(isFailedSessionState("uploading")).toBe(false);
  });

  it("epost 카테고리를 식별한다", () => {
    expect(isEpostCategory("epost_pobox_full")).toBe(true);
    expect(isEpostCategory("epost_bulk_full")).toBe(true);
    expect(isEpostCategory("roadname_hangul_full")).toBe(false);
  });

  it("12개 reconcile issue_type 라벨이 모두 매핑된다", () => {
    expect(Object.keys(reconcileIssueLabels)).toHaveLength(12);
    expect(reconcileIssueLabels.hash_mismatch).toBe("해시 불일치");
  });

  it("YYYYMM 검증과 제안값을 만든다", () => {
    expect(isValidYyyymm("202606")).toBe(true);
    expect(isValidYyyymm("20266")).toBe(false);
    expect(isValidYyyymm("2026-06")).toBe(false);
    expect(suggestYyyymm(new Date("2026-06-14T00:00:00Z"))).toBe("202606");
    expect(suggestYyyymm(new Date("2026-01-01T00:00:00Z"))).toBe("202601");
  });

  it("rebuild 강제 승급 확인 문구를 만든다", () => {
    expect(rebuildPromoteConfirmation("ms_42")).toBe("REBUILD-PROMOTE ms_42");
  });

  it("hash를 12자로 줄인다", () => {
    expect(shortHash(null)).toBe("-");
    expect(shortHash("abc")).toBe("abc");
    expect(shortHash("0123456789abcdef")).toBe("0123456789ab…");
  });

  it("경로 빌더가 v1 admin 경로를 만든다", () => {
    expect(sourceFilesPaths.uploadSession("u1")).toBe(
      "/admin/source-files/upload-sessions/u1"
    );
    expect(sourceFilesPaths.matchSetRebuildDb("m1")).toBe(
      "/admin/source-match-sets/m1/rebuild-db"
    );
    expect(sourceFilesPaths.reconcileItems("r1", { state: "open" })).toBe(
      "/admin/source-files/reconcile/r1/items?state=open"
    );
    expect(sourceFilesPaths.epostFetch()).toBe("/admin/source-files/epost-fetch");
  });
});

describe("live upload SSE stream cap (#512)", () => {
  function resumable(id: string, updatedAt: string | null): UploadSessionStatus {
    return {
      ...session("uploading"),
      upload_session_id: id,
      created_at: "2026-06-01T00:00:00Z",
      updated_at: updatedAt
    } as unknown as UploadSessionStatus;
  }

  it("기본 상한은 브라우저 6-connection 한도보다 충분히 작다", () => {
    // An EventSource holds a connection for its lifetime; leave headroom for navigation.
    expect(MAX_LIVE_UPLOAD_STREAMS).toBeGreaterThan(0);
    expect(MAX_LIVE_UPLOAD_STREAMS).toBeLessThan(6);
  });

  it("세션이 많아도 상한만큼만 구독한다 (연결 고갈 회귀 방지)", () => {
    const sessions = Array.from({ length: 9 }, (_, i) =>
      resumable(`s${i}`, `2026-06-0${(i % 9) + 1}T00:00:00Z`)
    );
    const live = selectLiveUploadStreamIds(sessions);
    expect(live.size).toBe(MAX_LIVE_UPLOAD_STREAMS);
  });

  it("가장 최근 갱신된 세션을 고른다", () => {
    const sessions = [
      resumable("old", "2026-06-01T00:00:00Z"),
      resumable("newest", "2026-06-09T00:00:00Z"),
      resumable("mid", "2026-06-05T00:00:00Z")
    ];
    expect([...selectLiveUploadStreamIds(sessions, 2)].sort()).toEqual(["mid", "newest"]);
  });

  it("updated_at이 없으면 created_at으로 대체하고, 둘 다 없어도 throw하지 않는다", () => {
    const withCreatedOnly = {
      ...resumable("created-only", null),
      created_at: "2026-06-08T00:00:00Z"
    } as unknown as UploadSessionStatus;
    const undated = {
      ...resumable("undated", null),
      created_at: null
    } as unknown as UploadSessionStatus;
    const live = selectLiveUploadStreamIds(
      [undated, withCreatedOnly, resumable("older", "2026-06-02T00:00:00Z")],
      1
    );
    expect([...live]).toEqual(["created-only"]);
  });

  it("세션 수가 상한 이하면 전부 구독한다", () => {
    const sessions = [resumable("a", "2026-06-01T00:00:00Z")];
    expect(selectLiveUploadStreamIds(sessions).size).toBe(1);
  });

  it("같은 입력에 대해 선택이 안정적이다 (EventSource 재개폐 방지)", () => {
    // Same activity stamp on every row -> id tiebreaker keeps the set stable.
    const sessions = ["c", "a", "b", "d"].map((id) => resumable(id, "2026-06-01T00:00:00Z"));
    const first = [...selectLiveUploadStreamIds(sessions, 2)].sort();
    const shuffled = [sessions[2], sessions[0], sessions[3], sessions[1]];
    expect([...selectLiveUploadStreamIds(shuffled, 2)].sort()).toEqual(first);
  });

  it("max가 0 이하면 아무것도 구독하지 않는다", () => {
    expect(selectLiveUploadStreamIds([resumable("a", null)], 0).size).toBe(0);
  });

  it("입력 배열을 변형하지 않는다", () => {
    const sessions = [
      resumable("a", "2026-06-01T00:00:00Z"),
      resumable("b", "2026-06-09T00:00:00Z")
    ];
    const order = sessions.map((s) => s.upload_session_id);
    selectLiveUploadStreamIds(sessions, 1);
    expect(sessions.map((s) => s.upload_session_id)).toEqual(order);
  });
});
