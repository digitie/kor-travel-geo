import { expect, test } from "@playwright/test";
import { installSourceFilesMock, makeUploadSession } from "./fixtures/source-files";

// T-261 단계별 e2e: 구조 검증. 원천 파일 그룹의 구조 검증 결과를 성공/warning/failed로 구분하고
// 사유를 표시하는 경로를 T-225 공용 하네스로 백엔드 없이 고정한다. 그룹 목록의 상태 배지(성공
// available / 실패 failed_structure)와 재검증(groupValidate) 결과(severity + 사유)를 검증한다.
// (의존: T-225)

test.describe("구조 검증 /admin/source-files (T-261)", () => {
  test("그룹 목록이 구조 상태(성공 available / 실패 failed_structure)를 구분 표시한다", async ({
    page
  }) => {
    await installSourceFilesMock(page, {
      uploadSessions: [
        makeUploadSession({
          upload_session_id: "s_ok",
          source_file_group_id: "grp_ok",
          state: "available",
          registration_state: "registered"
        }),
        makeUploadSession({
          upload_session_id: "s_bad",
          source_file_group_id: "grp_bad",
          category: "locsum_full",
          user_yyyymm: "202604",
          state: "failed_structure",
          error_message: "구조 검증 실패: 필수 컬럼 누락"
        })
      ]
    });
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "목록" }).click();

    const groupsPanel = page.locator(".panel", { hasText: "원천 파일 그룹" });
    await expect(groupsPanel.getByText("등록된 원천 파일 그룹이 없습니다.")).toHaveCount(0);
    // 성공(available)·실패(failed_structure) 상태 배지가 각각 보인다.
    await expect(groupsPanel.locator("span.status", { hasText: "available" })).toBeVisible();
    await expect(groupsPanel.locator("span.status", { hasText: "failed_structure" })).toBeVisible();
  });

  test("재검증: warning 결과와 사유가 최근 결과에 표시된다", async ({ page }) => {
    await installSourceFilesMock(page, {
      uploadSessions: [
        makeUploadSession({
          upload_session_id: "s1",
          source_file_group_id: "grp_warn",
          state: "available",
          registration_state: "registered"
        })
      ],
      responses: {
        "/validate": {
          source_file_group_id: "grp_warn",
          state: "warning",
          warnings: ["기준월 혼합: 202603/202604"]
        }
      }
    });
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "목록" }).click();

    // 아이콘 버튼 → 확인 다이얼로그 → 실행 (파괴적/부하 액션 공통 확인 단계).
    await page.getByRole("button", { name: "재검증", exact: true }).click();
    await page
      .getByRole("alertdialog", { name: "원천 그룹 재검증" })
      .getByRole("button", { name: "재검증 실행" })
      .click();

    const result = page.locator(".panel", { hasText: "최근 결과" });
    await expect(result.locator("pre")).toContainText('"state": "warning"');
    await expect(result.locator("pre")).toContainText("기준월 혼합: 202603/202604");
  });

  test("재검증: failed 결과와 사유가 최근 결과에 표시된다", async ({ page }) => {
    await installSourceFilesMock(page, {
      uploadSessions: [
        makeUploadSession({
          upload_session_id: "s1",
          source_file_group_id: "grp_fail",
          state: "available",
          registration_state: "registered"
        })
      ],
      responses: {
        "/validate": {
          source_file_group_id: "grp_fail",
          state: "failed",
          errors: ["필수 파일 누락: tl_locsum_entrc"]
        }
      }
    });
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "목록" }).click();

    await page.getByRole("button", { name: "재검증", exact: true }).click();
    await page
      .getByRole("alertdialog", { name: "원천 그룹 재검증" })
      .getByRole("button", { name: "재검증 실행" })
      .click();

    const result = page.locator(".panel", { hasText: "최근 결과" });
    await expect(result.locator("pre")).toContainText('"state": "failed"');
    await expect(result.locator("pre")).toContainText("필수 파일 누락: tl_locsum_entrc");
  });
});
