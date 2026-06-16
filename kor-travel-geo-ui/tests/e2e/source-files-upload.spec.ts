import { expect, test } from "@playwright/test";
import { installSourceFilesMock } from "./fixtures/source-files";

// T-259 단계별 e2e: 업로드 적재. 업로드 탭에서 category 선택·기준월 입력·파일 선택 →
// 세션 생성 → multipart(initiate/part/complete) → register 성공 경로를 T-225 공용 하네스로
// 백엔드 없이 고정한다. (의존: T-225)

const ROAD_CATEGORY = "roadname_hangul_full";

function smallZip() {
  return {
    name: "juso_202606.zip",
    mimeType: "application/zip",
    buffer: Buffer.from("x".repeat(256))
  };
}

test.describe("업로드 적재 /admin/source-files (T-259)", () => {
  test("업로드 버튼은 파일 + 유효 기준월 전에는 비활성이다", async ({ page }) => {
    await installSourceFilesMock(page);
    await page.goto("/admin/source-files");

    const card = page.locator(".source-card", { hasText: "도로명주소 한글 전체분" });
    const uploadButton = card.getByRole("button", { name: "업로드" });
    await expect(uploadButton).toBeDisabled();

    // 기준월만 입력 → 여전히 비활성(파일 없음).
    await card.getByPlaceholder("예: 202606").fill("202606");
    await expect(uploadButton).toBeDisabled();

    // 파일까지 선택 → 활성.
    await card.getByLabel("도로명주소 한글 전체분 파일 선택").setInputFiles(smallZip());
    await expect(uploadButton).toBeEnabled();
  });

  test("category·기준월·파일 → 세션 생성·multipart·register 성공 경로", async ({ page }) => {
    await installSourceFilesMock(page);
    await page.goto("/admin/source-files");

    const card = page.locator(".source-card", { hasText: "도로명주소 한글 전체분" });
    await card.getByPlaceholder("예: 202606").fill("202606");
    await card.getByLabel("도로명주소 한글 전체분 파일 선택").setInputFiles(smallZip());

    // 세션 생성 요청(category·user_yyyymm 포함)을 캡처한다.
    const createRequest = page.waitForRequest(
      (req) => req.url().endsWith("/admin/source-files/upload-sessions") && req.method() === "POST"
    );
    // multipart 적재 + register 경로가 발동하는지 확인한다.
    const initiateRequest = page.waitForRequest(
      (req) => /\/files\/[^/]+\/multipart$/.test(new URL(req.url()).pathname) && req.method() === "POST"
    );
    const completeRequest = page.waitForRequest(
      (req) => req.url().includes("/multipart/complete") && req.method() === "POST"
    );
    const registerRequest = page.waitForRequest(
      (req) => req.url().endsWith("/register") && req.method() === "POST"
    );

    await card.getByRole("button", { name: "업로드" }).click();

    const createBody = (await createRequest).postDataJSON();
    expect(createBody.category).toBe(ROAD_CATEGORY);
    expect(createBody.user_yyyymm).toBe("202606");
    await initiateRequest;
    await completeRequest;
    await registerRequest;

    // multipart 진행 표시(슬롯 'archive' 완료)와 register 결과가 노출된다.
    await expect(card.getByText("완료").first()).toBeVisible();
    const result = page.locator(".panel", { hasText: "최근 결과" });
    await expect(result.locator("pre")).toContainText('"registration_state": "registered"');
  });
});
