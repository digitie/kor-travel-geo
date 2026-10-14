import { describe, expect, it } from "vitest";
import type { ServingRelease } from "@/lib/api";
import { fingerprintFailureNote, recentFingerprintsMissing, sameDataAsPrevious, validDataToken } from "@/lib/dataset-token";

const token = "dd1-" + "a".repeat(32);
const old: ServingRelease = { serving_release_id: "old", dataset_snapshot_id: "s0", state: "superseded", release_kind: "full_load", mv_name: "mv", created_at: "2026-10-13T00:00:00Z", activated_at: "2026-10-13T01:00:00Z", data_token: token };
const current: ServingRelease = { ...old, serving_release_id: "now", state: "active", previous_serving_release_id: "old", version_token: "dv1-" + "b".repeat(32) };
describe("서빙 데이터 지문 비교", () => {
  it.each([undefined, null, "", "dd1-a", "dv1-" + "a".repeat(32), "dd1-" + "A".repeat(32)])("%s는 동일성을 판단하지 않는다", value => expect(validDataToken(value)).toBeNull());
  it("릴리스 토큰이 달라도 같은 데이터 지문만 동일 배지를 허용한다", () => expect(sameDataAsPrevious(current, [old, current])).toBe(true));
  it("행 순서 대신 previous_serving_release_id를 따른다", () => expect(sameDataAsPrevious(current, [{ ...old, serving_release_id: "other", data_token: "dd1-" + "c".repeat(32) }, current, old])).toBe(true));
  it("pending 상태에서는 지문과 활성화 시각이 남아도 동일을 추측하지 않는다", () => expect(sameDataAsPrevious({ ...current, state: "pending" }, [old])).toBe(false));
  it("비교 이력이 없으면 동일을 추측하지 않는다", () => expect(sameDataAsPrevious(current, [current])).toBe(false));
  it("누락 두 건은 동일이 아니며 실제 직전 활성화일 때만 경고한다", () => {
    const rows = [{ ...current, data_token: null }, { ...old, data_token: null }];
    expect(sameDataAsPrevious(rows[0], rows)).toBe(false); expect(recentFingerprintsMissing(rows)).toBe(true);
    expect(recentFingerprintsMissing([rows[0], { ...rows[1], state: "pending", activated_at: null }])).toBe(false);
    expect(recentFingerprintsMissing([rows[0], { ...rows[1], serving_release_id: "unrelated" }])).toBe(false);
  });
  it("현재 지문 복구 뒤에는 누락 이력 경고가 사라진다", () => expect(recentFingerprintsMissing([current, { ...old, data_token: null }])).toBe(false));
  it("지문 실패의 마지막 사유 코드만 도구 설명에 남긴다", () => expect(fingerprintFailureNote({ ...current, notes: "operator memo data_fingerprint_failed: timeout extra memo" })).toBe("data_fingerprint_failed: timeout"));
});
