import { expect, test } from "@playwright/test";
import { installSourceFilesMock } from "./fixtures/source-files";

// /admin/source-files (T-209) e2e. 백엔드 admin API는 page.route로 목킹하므로 DB/백엔드 없이
// UI 단독으로 5개 기능 탭 + 동적 검증 케이스 탭과 핵심 상호작용을 검증한다.
// mock fixture는 T-225 공용 하네스(`./fixtures/source-files`)를 사용한다 — 이 spec의 기대값은
// 하네스 기본 fixture와 동일하다.

const mockSourceFilesApi = installSourceFilesMock;

test.describe("원천 파일 관리 /admin/source-files", () => {
  test("5개 기능 탭 + 검증 케이스 탭을 렌더한다", async ({ page }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");

    const tabList = page.getByRole("tablist", { name: "원천 파일 관리 탭" });
    await expect(tabList).toBeVisible();
    for (const name of ["업로드", "목록", "매칭 세트", "RustFS 정합성", "현재 구성", "검증 케이스"]) {
      await expect(page.getByRole("tab", { name })).toBeVisible();
    }
  });

  test("업로드 탭: 카테고리 카드와 epost 받기 버튼(활성)을 보여 준다", async ({ page }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");

    await expect(page.getByText("도로명주소 한글 전체분")).toBeVisible();
    const epostCard = page.locator(".source-card", { hasText: "epost 사서함" });
    await expect(epostCard.getByRole("button", { name: "epost 받기" })).toBeEnabled();
  });

  test("업로드 탭: serving_usage 분류와 현재 서빙 포함/미포함을 구분 표시한다 (T-221/T-224)", async ({
    page
  }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");

    // serving core(좌표 정본) → '활용 중(서빙)' + 활성 세트에 포함되어 '현재 서빙 포함'.
    const roadCard = page.locator(".source-card", { hasText: "도로명주소 한글 전체분" });
    await expect(roadCard.getByText("활용 중(서빙)")).toBeVisible();
    await expect(roadCard.getByText("현재 서빙 포함")).toBeVisible();

    // 별도 기능 후보(epost) → serving augmentation처럼 보이지 않고 '현재 서빙 미포함'.
    const epostCard = page.locator(".source-card", { hasText: "epost 사서함" });
    await expect(epostCard.getByText("별도 기능 후보(서빙 미반영)")).toBeVisible();
    await expect(epostCard.getByText("현재 서빙 미포함")).toBeVisible();
    await expect(epostCard.getByText(/등록됨 ≠ 활용 중/)).toBeVisible();
  });

  test("탭 교차 흐름: 모든 기능 탭을 오가도 선택 상태와 콘텐츠가 유지된다 (smoke)", async ({
    page
  }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");
    await expect(page.getByText("도로명주소 한글 전체분")).toBeVisible();

    for (const name of ["목록", "매칭 세트", "RustFS 정합성", "현재 구성", "검증 케이스", "업로드"]) {
      await page.getByRole("tab", { name }).click();
      await expect(page.getByRole("tab", { name, selected: true })).toBeVisible();
    }
    // 마지막 업로드 탭으로 돌아왔을 때 카테고리 카드가 다시 보인다.
    await expect(page.getByText("도로명주소 한글 전체분")).toBeVisible();
  });

  test("매칭 세트 탭: 활성 세트와 무결성 경보를 표시한다", async ({ page }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "매칭 세트" }).click();

    // 세트명은 목록 span + 상세 패널 제목 두 곳에 나타나므로 first()로 한정한다.
    await expect(page.getByText("활성 세트").first()).toBeVisible();
    await expect(page.getByText(/무결성 경보/).first()).toBeVisible();
  });

  test("RustFS 정합성 탭: 실행/정리 대상/용량을 표시한다", async ({ page }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "RustFS 정합성" }).click();

    await expect(page.getByText("정합성 실행 (RustFS ⟷ DB)")).toBeVisible();
    await expect(page.getByText("객체 있으나 DB row 없음")).toBeVisible();
    await expect(page.getByRole("button", { name: /선택 항목 영구 삭제/ })).toBeVisible();
    await expect(page.getByText("용량 (capacity)")).toBeVisible();
  });

  test("검증 케이스 탭: registry에서 C1~C17를 동적으로 렌더한다", async ({ page }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "검증 케이스" }).click();

    await expect(page.getByRole("tab", { name: /C17/ })).toBeVisible();
  });

  test("RustFS 정합성 탭: 정리 대상 선택→typed confirmation→일괄 영구 삭제", async ({ page }) => {
    await mockSourceFilesApi(page);
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "RustFS 정합성" }).click();

    await page.getByLabel(/정리 대상 선택:/).check();
    await page.getByRole("button", { name: /선택 항목 영구 삭제/ }).click();

    const dialog = page.getByRole("dialog", { name: "원천 객체 영구 삭제" });
    await expect(dialog).toBeVisible();
    // T-226: 위험작업 필요 역할 안내(destructive_admin).
    await expect(dialog.getByText(/필요 역할/)).toContainText("destructive_admin");
    const exec = dialog.getByRole("button", { name: /영구 삭제 실행/ });
    await expect(exec).toBeDisabled();
    await dialog.getByLabel("hard-delete 확인 문구").fill("HARD-DELETE-SOURCES");
    await expect(exec).toBeEnabled();
    await exec.click();

    // 구조화된 결과 요약(raw JSON 아님)
    const result = page.locator(".panel", { hasText: "최근 결과" });
    await expect(result.getByText("영구 삭제")).toBeVisible();
  });
});
