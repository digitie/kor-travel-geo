import { expect, test } from "@playwright/test";
import {
  installSourceFilesMock,
  makeProgressEvent,
  makeUploadSession
} from "./fixtures/source-files";

// T-225 공용 source-files fake-API 하네스 스모크. T-259~T-263 단계별 e2e가 의존할 knob —
// 기본 fixture 렌더, 오류 주입, upload-session 상태머신, SSE 프레임 전달 — 이 동작함을 고정한다.
// (탭/매칭/정합성 세부 흐름은 source-files.spec.ts가 같은 하네스 기본값으로 검증한다.)

test.describe("source-files fake-API 하네스 (T-225)", () => {
  test("기본 fixture로 /admin/source-files가 렌더된다", async ({ page }) => {
    await installSourceFilesMock(page);
    await page.goto("/admin/source-files");

    await expect(page.getByRole("tablist", { name: "원천 파일 관리 탭" })).toBeVisible();
    await expect(page.getByText("도로명주소 한글 전체분")).toBeVisible();
  });

  test("오류 주입: 엔드포인트 500을 주입해도 콘솔이 죽지 않는다", async ({ page }) => {
    await installSourceFilesMock(page, {
      errors: [{ path: "/source-file-categories", status: 500 }]
    });
    const categoriesResponse = page.waitForResponse((res) =>
      res.url().includes("/source-file-categories")
    );
    await page.goto("/admin/source-files");

    // 하네스가 실제로 500을 돌려준다(오류 주입 동작 확인).
    expect((await categoriesResponse).status()).toBe(500);
    // 카탈로그 로드 실패에도 탭 셸은 렌더된다.
    await expect(page.getByRole("tablist", { name: "원천 파일 관리 탭" })).toBeVisible();
  });

  test("upload-session 상태머신 + SSE 프레임이 재개 목록에 반영된다", async ({ page }) => {
    await installSourceFilesMock(page, {
      uploadSessions: [
        makeUploadSession({ upload_session_id: "us_live", state: "uploading", user_yyyymm: "202604" })
      ],
      sse: (sessionId) => ({
        frames: [makeProgressEvent(sessionId, { state: "uploading", progress: 0.5, stage: "multipart" })]
      })
    });
    await page.goto("/admin/source-files");

    const resumePanel = page.locator(".panel", { hasText: "재개 가능한 업로드" });
    await expect(resumePanel).toBeVisible();
    // 비어 있지 않고(상태머신 세션 제공), 세션 행이 보인다.
    await expect(resumePanel.getByText("재개할 수 있는 진행 중 세션이 없습니다.")).toHaveCount(0);
    await expect(resumePanel.getByText("202604")).toBeVisible();
    // SSE 프레임(progress 0.5)이 라이브 진행률 50%로 반영된다.
    await expect(resumePanel.getByText("50%")).toBeVisible();
  });
});
