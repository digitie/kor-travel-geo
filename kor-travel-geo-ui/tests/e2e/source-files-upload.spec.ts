import { expect, test } from "@playwright/test";
import { installSourceFilesMock, makeCategoryCatalog, makeFileSlot, makeUploadSession } from "./fixtures/source-files";

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
  test("시도별 세션 재개에서 완료 파일을 보존하고 남은 파일을 업로드·등록한다", async ({ page }) => {
    const category = { category: "electronic_map_full", label: "도로명주소 전자지도", role: "build_required", serving_usage: "serving_core", group_kind: "multi_part", optional: false, expected_member_kinds: [] };
    const slots = [makeFileSlot({ slot: "11", part_key: "11", part_label: "서울특별시", uploaded: true, received_bytes: 256 }), makeFileSlot({ slot: "12", part_key: "12", part_label: "전남광주통합특별시" })];
    const session = makeUploadSession({ category: "electronic_map_full", user_yyyymm: "202610", state: "uploading", group_kind: "multi_part", expected_file_count: 2, uploaded_file_count: 1, file_slots: slots });
    await installSourceFilesMock(page, { catalog: makeCategoryCatalog([category]) });
    const uploadedSlots: string[] = [];
    await page.route("**/api/proxy/v1/admin/source-files/upload-sessions**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path.endsWith("/upload-sessions") && request.method() === "POST") return route.fulfill({ status: 409, json: { detail: { session } } });
      if (path.endsWith("/multipart/complete")) {
        uploadedSlots.push(path.split("/files/")[1].split("/")[0]);
        return route.fulfill({ json: { ...session, uploaded_file_count: 2, file_slots: slots.map((slot) => ({ ...slot, uploaded: true })) } });
      }
      if (path.endsWith("/preview-validate")) return route.fulfill({ json: { outcome: "passed", parts: [] } });
      await route.fallback();
    });
    await page.goto("/admin/source-files");
    await page.getByRole("button", { name: "업로드 마법사", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("option", { name: /도로명주소 전자지도/ }).click();
    await dialog.getByRole("combobox", { name: "기준년월", exact: true }).fill("202610");
    await dialog.getByRole("button", { name: "다음", exact: true }).click();
    await dialog.getByRole("button", { name: "업로드 세션 열기", exact: true }).click();
    await expect(dialog.getByText("1/2 파일 업로드 완료")).toBeVisible();
    await dialog.getByLabel("전남광주통합특별시 파일 선택", { exact: true }).setInputFiles(smallZip());
    await expect(dialog.getByRole("button", { name: "다음", exact: true })).toBeEnabled();
    expect(uploadedSlots).toEqual(["12"]);
    await dialog.getByRole("button", { name: "다음", exact: true }).click();
    await dialog.getByRole("button", { name: "등록", exact: true }).click();
    await expect(dialog.getByText(/업로드가 등록됐습니다/)).toBeVisible();
  });
  test("20MiB 파일을 8MiB 이하 파트로 모두 전송한 뒤 등록한다", async ({ page }) => {
    await installSourceFilesMock(page);
    const partSizes: number[] = [];
    page.on("request", (request) => {
      if (request.method() === "PUT" && /\/multipart\/\d+$/.test(new URL(request.url()).pathname)) {
        partSizes.push(request.postDataBuffer()?.byteLength ?? 0);
      }
    });
    await page.goto("/admin/source-files");
    const card = page.locator(".source-card", { hasText: "도로명주소 한글 전체분" });
    await card.getByPlaceholder("예: 202606").fill("202606");
    await card.getByLabel("도로명주소 한글 전체분 파일 선택").setInputFiles({
      name: "large.zip", mimeType: "application/zip", buffer: Buffer.alloc(20 * 1024 * 1024)
    });
    const registered = page.waitForRequest(
      (request) => request.url().endsWith("/register") && request.method() === "POST"
    );
    await card.getByRole("button", { name: "업로드" }).click();
    await registered;
    expect(partSizes).toEqual([8 * 1024 * 1024, 8 * 1024 * 1024, 4 * 1024 * 1024]);
    await expect(card.getByText("완료").first()).toBeVisible();
  });

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
    // 실 백엔드는 confirm_user_yyyymm이 세션 user_yyyymm과 일치해야만 register를 허용한다
    // (RegisterRequest 필수 필드) — mock은 body를 검증하지 않아 이 필드 누락이 조용히
    // 통과했던 회귀(live e2e로 발견)를 여기서 고정한다.
    const registerBody = (await registerRequest).postDataJSON();
    expect(registerBody.confirm_user_yyyymm).toBe("202606");

    // multipart 진행 표시(슬롯 'archive' 완료)와 register 결과가 노출된다.
    await expect(card.getByText("완료").first()).toBeVisible();
    const result = page.locator(".panel", { hasText: "최근 결과" });
    await expect(result.locator("pre")).toContainText('"registration_state": "registered"');
  });
});
