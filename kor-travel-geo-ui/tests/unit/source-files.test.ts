import { describe, expect, it } from "vitest";
import {
  isEpostCategory,
  isFailedSessionState,
  isResumableSession,
  isValidYyyymm,
  rebuildPromoteConfirmation,
  reconcileIssueLabels,
  shortHash,
  sourceFilesPaths,
  suggestYyyymm,
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

describe("source-files helpers", () => {
  it("non-terminal 세션만 재개 가능으로 판정한다", () => {
    expect(isResumableSession(session("uploading"))).toBe(true);
    expect(isResumableSession(session("created"))).toBe(true);
    expect(isResumableSession(session("registered"))).toBe(false);
    expect(isResumableSession(session("cancelled"))).toBe(false);
    expect(isResumableSession(session("registration_expired"))).toBe(false);
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
  });
});
