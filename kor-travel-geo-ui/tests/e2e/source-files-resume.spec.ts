import { expect, test } from "@playwright/test";
import { installSourceFilesMock, makeUploadSession } from "./fixtures/source-files";

// T-260 단계별 e2e: 업로드 대기·재개·409 충돌. 중단된(비종료) 업로드의 재개 목록과,
// 같은 category·기준월로 새 세션을 만들 때의 409 중복 충돌 dialog(기존 세션 재개/닫기 =
// slot replace 진입점)를 T-225 공용 하네스로 백엔드 없이 고정한다. (의존: T-225)

function smallZip() {
  return { name: "juso.zip", mimeType: "application/zip", buffer: Buffer.from("x".repeat(128)) };
}

async function triggerCreate(page: import("@playwright/test").Page) {
  const card = page.locator(".source-card", { hasText: "도로명주소 한글 전체분" });
  await card.getByPlaceholder("예: 202606").fill("202606");
  await card.getByLabel("도로명주소 한글 전체분 파일 선택").setInputFiles(smallZip());
  await card.getByRole("button", { name: "업로드" }).click();
}

test.describe("업로드 대기·재개·409 /admin/source-files (T-260)", () => {
  test("재개 가능한 업로드: 비종료 세션이 재개 목록에 표시된다", async ({ page }) => {
    await installSourceFilesMock(page, {
      uploadSessions: [
        makeUploadSession({
          upload_session_id: "us_wip",
          state: "uploading",
          user_yyyymm: "202604",
          uploaded_file_count: 0,
          expected_file_count: 1
        })
      ]
    });
    await page.goto("/admin/source-files");

    const resumePanel = page.locator(".panel", { hasText: "재개 가능한 업로드" });
    await expect(resumePanel).toBeVisible();
    await expect(resumePanel.getByText("재개할 수 있는 진행 중 세션이 없습니다.")).toHaveCount(0);
    await expect(resumePanel.getByText("roadname_hangul_full", { exact: true })).toBeVisible();
    await expect(resumePanel.getByText("202604", { exact: true })).toBeVisible();
  });

  test("409 충돌: 중복 세션 dialog가 기존 세션 정보를 보여 준다", async ({ page }) => {
    const existing = makeUploadSession({
      upload_session_id: "us_existing",
      state: "uploading",
      uploaded_file_count: 1,
      expected_file_count: 2
    });
    await installSourceFilesMock(page, {
      errors: [
        { path: /\/upload-sessions$/, method: "POST", status: 409, body: JSON.stringify({ detail: existing }) }
      ]
    });
    await page.goto("/admin/source-files");
    await triggerCreate(page);

    const dialog = page.getByRole("dialog", { name: "중복 업로드 세션" });
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByText("이미 진행 중인 업로드 세션이 있습니다", { exact: true })
    ).toBeVisible();
    await expect(dialog.getByText("us_existing", { exact: true })).toBeVisible();
    // 업로드 슬롯 진척(1/2)도 노출된다.
    await expect(dialog.getByText("1/2", { exact: true })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "기존 세션 재개" })).toBeVisible();
  });

  test("409 충돌: 기존 세션 재개 → 재개 결과 노출·dialog 닫힘 (slot replace 진입)", async ({
    page
  }) => {
    const existing = makeUploadSession({ upload_session_id: "us_existing", state: "uploading" });
    await installSourceFilesMock(page, {
      errors: [
        { path: /\/upload-sessions$/, method: "POST", status: 409, body: JSON.stringify({ detail: existing }) }
      ]
    });
    await page.goto("/admin/source-files");
    await triggerCreate(page);

    const dialog = page.getByRole("dialog", { name: "중복 업로드 세션" });
    await dialog.getByRole("button", { name: "기존 세션 재개" }).click();

    await expect(dialog).toBeHidden();
    const result = page.locator(".panel", { hasText: "최근 결과" });
    await expect(result.locator("pre")).toContainText('"resumed_session": "us_existing"');
  });

  test("409 충돌: 닫기로 재개 없이 dialog를 닫는다", async ({ page }) => {
    const existing = makeUploadSession({ upload_session_id: "us_existing", state: "uploading" });
    await installSourceFilesMock(page, {
      errors: [
        { path: /\/upload-sessions$/, method: "POST", status: 409, body: JSON.stringify({ detail: existing }) }
      ]
    });
    await page.goto("/admin/source-files");
    await triggerCreate(page);

    const dialog = page.getByRole("dialog", { name: "중복 업로드 세션" });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "닫기" }).click();
    await expect(dialog).toBeHidden();
  });
});
