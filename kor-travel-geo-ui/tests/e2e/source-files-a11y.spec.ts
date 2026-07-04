import { expect, test } from "@playwright/test";
import { installSourceFilesMock, makeUploadSession } from "./fixtures/source-files";

// /admin/source-files 접근성·회복성 e2e (T-227). 기존 표면(원천 파일 관리)의 키보드(탭 활성·
// 위험 다이얼로그 focus 진입/trap/Esc/포커스 복귀)와 회복성(다중 엔드포인트 500·SSE 끊김·느린
// API 로딩 안내·refresh 재적재)을 백엔드 없이 T-225 공용 하네스(installSourceFilesMock)로 고정한다.
// 신규 backups 표면 a11y는 backups-a11y.spec.ts(T-258)가 담당하므로 여기서는 중복을 피한다.

test.describe("원천 파일 관리 접근성·회복성 /admin/source-files (T-227)", () => {
  test("탭: 키보드(focus→Enter)로 탭을 전환할 수 있다", async ({ page }) => {
    await installSourceFilesMock(page);
    await page.goto("/admin/source-files");

    await page.getByRole("tab", { name: "매칭 세트" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("tab", { name: "매칭 세트", selected: true })).toBeVisible();
  });

  test("hard-delete 다이얼로그: 확인 입력 포커스·Tab 트랩·Esc 닫힘·트리거로 포커스 복귀", async ({
    page
  }) => {
    await installSourceFilesMock(page);
    await page.goto("/admin/source-files");
    await page.getByRole("tab", { name: "RustFS 정합성" }).click();

    await page.getByLabel(/정리 대상 선택:/).check();
    const trigger = page.getByRole("button", { name: /선택 항목 영구 삭제/ });
    await trigger.focus();
    await page.keyboard.press("Enter");

    const dialog = page.getByRole("alertdialog", { name: "원천 객체 영구 삭제" });
    await expect(dialog).toBeVisible();
    // 열리면 포커스가 확인 입력으로 이동한다.
    await expect(page.getByLabel("hard-delete 확인 문구")).toBeFocused();

    // Tab 트랩: 마지막 focusable(취소)에서 Tab → 첫 focusable(manifest_ack 체크)로 순환(밖으로 안 나감).
    await dialog.getByRole("button", { name: "취소" }).focus();
    await page.keyboard.press("Tab");
    await expect(dialog.getByRole("checkbox", { name: /manifest 없이 진행/ })).toBeFocused();

    // Esc로 닫히고(키보드 only) 포커스가 트리거로 복귀한다.
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("회복성: 여러 엔드포인트 500이어도 콘솔이 죽지 않고 탭 전환이 된다", async ({ page }) => {
    await installSourceFilesMock(page, {
      errors: [
        { path: "/source-file-categories", status: 500 },
        { path: "/source-match-sets", status: 500 },
        { path: "/reconcile-runs", status: 500 }
      ]
    });
    await page.goto("/admin/source-files");

    // 탭 셸이 살아 있고(앱이 죽지 않음) 오류 이후에도 탭 전환이 가능하다.
    await expect(page.getByRole("tablist", { name: "원천 파일 관리 탭" })).toBeVisible();
    await page.getByRole("tab", { name: "매칭 세트" }).click();
    await expect(page.getByRole("tab", { name: "매칭 세트", selected: true })).toBeVisible();
  });

  test("회복성: SSE(/events) 끊겨도 재개 세션 행이 폴링 상태로 렌더된다", async ({ page }) => {
    await installSourceFilesMock(page, {
      uploadSessions: [
        makeUploadSession({
          upload_session_id: "us_live",
          state: "uploading",
          user_yyyymm: "202604"
        })
      ],
      sse: () => ({ status: 500 }) // 스트림 드롭(>=400)
    });
    await page.goto("/admin/source-files");

    const resumePanel = page.locator(".panel", { hasText: "재개 가능한 업로드" });
    await expect(resumePanel).toBeVisible();
    // 스트림이 끊겨도(폴링 fallback) 세션 행은 보인다.
    await expect(resumePanel.getByText("재개할 수 있는 진행 중 세션이 없습니다.")).toHaveCount(0);
    await expect(resumePanel.getByText("202604")).toBeVisible();
  });

  test("느린 API: 카테고리 로딩 안내 후 카탈로그가 채워진다 (skeleton/slow API)", async ({
    page
  }) => {
    await installSourceFilesMock(page);
    // 카테고리 응답을 게이트로 잡아 로딩 안내를 결정적으로 관찰한다(타이밍 race 없이).
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/source-file-categories**", async (route) => {
      await gate;
      await route.fallback(); // 해제 후 하네스 기본 응답으로 위임
    });
    await page.goto("/admin/source-files");

    await expect(page.getByText("카테고리 카탈로그를 불러오는 중…")).toBeVisible();
    release();
    await expect(page.getByText("도로명주소 한글 전체분")).toBeVisible();
  });

  test("회복성: refresh 후 서버 상태(카테고리)가 다시 적재된다", async ({ page }) => {
    await installSourceFilesMock(page);
    await page.goto("/admin/source-files");
    await expect(page.getByText("도로명주소 한글 전체분")).toBeVisible();

    await page.reload();
    await expect(page.getByText("도로명주소 한글 전체분")).toBeVisible();
  });
});
