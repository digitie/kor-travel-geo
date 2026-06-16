import { expect, test } from "@playwright/test";
import {
  installSourceFilesMock,
  makeMatchSetDetail,
  makeMatchSets
} from "./fixtures/source-files";

// T-262 단계별 e2e: 매칭 세트. match set 검증(invalid→revalidatable)·활성화·integrity_alert
// 표시를 T-225 공용 하네스로 백엔드 없이 고정한다. (match set '생성'은 매칭 세트 탭에 전용 UI가
// 없고 CLI/업로드 register로 out-of-band 수행되므로 여기서는 lifecycle 액션을 고정한다.)
// (의존: T-225)

const ACTIVE = makeMatchSets()[0]; // ms_active · active · integrity_alert:true · "활성 세트"

test.describe("매칭 세트 /admin/source-files (T-262)", () => {
  test("목록: 상태 라벨과 integrity_alert 배지를 구분 표시한다", async ({ page }) => {
    const invalid = {
      ...ACTIVE,
      source_match_set_id: "ms_invalid",
      name: "무효 세트",
      state: "invalid",
      integrity_alert: false,
      integrity_alert_at: null,
      integrity_alert_detail: null
    };
    await installSourceFilesMock(page, {
      matchSets: [ACTIVE, invalid],
      matchSetDetail: makeMatchSetDetail(ACTIVE)
    });
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    const list = page.locator(".report-list");
    await expect(list.getByText("활성 세트")).toBeVisible();
    await expect(list.getByText("무효 세트")).toBeVisible();
    await expect(list.getByText("활성", { exact: true })).toBeVisible();
    await expect(list.getByText("무효", { exact: true })).toBeVisible();
    await expect(list.getByText("무결성 경보")).toBeVisible();
  });

  test("세부: integrity_alert 경보 박스(alert)와 detail을 표시한다", async ({ page }) => {
    await installSourceFilesMock(page); // 기본: ms_active(alert) + 상세
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    // 경보 박스의 제목(괄호 표기)은 detail 전용 — 목록 배지 '무결성 경보'와 구분된다.
    const alertBox = page.locator(".confirm-box[role='alert']");
    await expect(alertBox).toBeVisible();
    await expect(alertBox).toContainText("무결성 경보 (integrity_alert)");
    await expect(alertBox).toContainText("hash_mismatch");
  });

  test("검증: invalid 세트 run-validation이 revalidatable 판정을 노출한다", async ({ page }) => {
    const invalid = {
      ...ACTIVE,
      source_match_set_id: "ms_inv",
      name: "무효 세트",
      state: "invalid",
      integrity_alert: false,
      integrity_alert_at: null,
      integrity_alert_detail: null
    };
    await installSourceFilesMock(page, {
      matchSets: [invalid],
      matchSetDetail: makeMatchSetDetail(invalid),
      responses: {
        "/run-validation": {
          source_match_set_id: "ms_inv",
          state: "revalidatable",
          message: "재검증 가능: 누락 원천 재업로드 후 재검증하세요"
        }
      }
    });
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    await page.getByRole("button", { name: "run-validation", exact: true }).click();

    const result = page.locator(".panel", { hasText: "최근 결과" });
    await expect(result.locator("pre")).toContainText('"state": "revalidatable"');
    await expect(result.locator("pre")).toContainText("재검증 가능");
  });

  test("활성화: activate가 active 전이를 노출한다", async ({ page }) => {
    const validated = {
      ...ACTIVE,
      source_match_set_id: "ms_val",
      name: "검증 세트",
      state: "validated",
      integrity_alert: false,
      integrity_alert_at: null,
      integrity_alert_detail: null
    };
    await installSourceFilesMock(page, {
      matchSets: [validated],
      matchSetDetail: makeMatchSetDetail(validated),
      responses: {
        "/activate": { source_match_set_id: "ms_val", state: "active", activated: true }
      }
    });
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    await page.getByRole("button", { name: "activate", exact: true }).click();

    const result = page.locator(".panel", { hasText: "최근 결과" });
    await expect(result.locator("pre")).toContainText('"state": "active"');
    await expect(result.locator("pre")).toContainText('"activated": true');
  });
});
