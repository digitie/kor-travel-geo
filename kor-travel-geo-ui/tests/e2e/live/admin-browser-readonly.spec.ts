import { expect, test } from "@playwright/test";

import { ADMIN_PAGES } from "../../../lib/admin-pages";
import {
  LIVE_TIMEOUT,
  expectNoErrorScreen,
  isLiveE2EEnabled,
  loginLiveAdminPage
} from "./_live";

// LIVE admin browser read-only coverage.
//
// These drive the real UI against the real backend. They navigate and switch tabs only; they
// do not submit forms or click destructive/action buttons.
//
// 페이지 h1은 lib/admin-pages.ts(ADMIN_PAGES)와 단일 소스로 동기화한다.

async function gotoAdmin(page: import("@playwright/test").Page, path: string, heading: string) {
  await page.goto(path);
  await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible({
    timeout: LIVE_TIMEOUT
  });
  await expectNoErrorScreen(page);
}

test.describe("LIVE admin browser read-only pages", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdminPage(page, "/admin/settings");
  });

  test("/admin/load points operators to Source Files", async ({ page }) => {
    await gotoAdmin(page, "/admin/load", ADMIN_PAGES.load.title);
    await expect(page.getByRole("heading", { name: "적재 화면 안내" })).toBeVisible();
    await expect(page.getByRole("link", { name: /원천 파일 화면으로 이동/ })).toBeVisible();
  });

  test("/admin/cache renders cache metrics counters", async ({ page }) => {
    await gotoAdmin(page, "/admin/cache", ADMIN_PAGES.cache.title);
    await expect(page.getByRole("heading", { name: "캐시 지표" })).toBeVisible();
    await expect(page.getByText("entries")).toBeVisible();
    await expect(page.getByText("hits")).toBeVisible();
    await expect(page.getByText("expired")).toBeVisible();
  });

  test("/admin/logs renders the log tail panel", async ({ page }) => {
    await gotoAdmin(page, "/admin/logs", ADMIN_PAGES.logs.title);
    await expect(page.getByRole("heading", { name: "최근 로그" })).toBeVisible();
    await expect(page.locator("pre.json-box")).toBeVisible({ timeout: LIVE_TIMEOUT });
  });

  test("/admin/settings renders VWorld and RustFS panels", async ({ page }) => {
    await gotoAdmin(page, "/admin/settings", ADMIN_PAGES.settings.title);
    await expect(page.getByRole("heading", { name: "VWorld 인증키" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "현재 적용 상태" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "RustFS 저장소" })).toBeVisible();
  });

  test("/admin/settings exposes the VWorld key input without logging the key", async ({
    page
  }) => {
    await gotoAdmin(page, "/admin/settings", ADMIN_PAGES.settings.title);
    // exact:true 필수 — HelpTip 버튼의 aria-label("VWorld 인증키 도움말")과 substring 충돌 방지.
    await expect(page.getByLabel("VWorld 인증키", { exact: true })).toBeVisible({
      timeout: LIVE_TIMEOUT
    });
    await expect(page.getByText("지도 렌더링")).toBeVisible();
  });

  test("/admin/settings exposes RustFS storage fields", async ({ page }) => {
    await gotoAdmin(page, "/admin/settings", ADMIN_PAGES.settings.title);
    await expect(page.getByLabel("Endpoint URL")).toBeVisible({ timeout: LIVE_TIMEOUT });
    await expect(page.getByLabel("Bucket")).toBeVisible();
    await expect(page.getByLabel("Prefix")).toBeVisible();
    await expect(page.getByLabel("보존 기간")).toBeVisible();
  });

  test("/admin/files renders the unified file inventory", async ({ page }) => {
    await gotoAdmin(page, "/admin/files", ADMIN_PAGES.files.title);
    await expect(page.getByRole("heading", { name: "파일 인벤토리" })).toBeVisible();
    await expect(page.getByRole("table", { name: "파일 인벤토리 목록" })).toBeVisible({
      timeout: LIVE_TIMEOUT
    });
    await expect(page.getByText("전체 파일")).toBeVisible();
  });

  test("/admin/tables renders search and refresh controls", async ({ page }) => {
    await gotoAdmin(page, "/admin/tables", ADMIN_PAGES.tables.title);
    await expect(page.getByRole("heading", { name: "PostgreSQL 테이블", exact: true })).toBeVisible();
    await expect(page.getByPlaceholder("테이블 검색")).toBeVisible({ timeout: LIVE_TIMEOUT });
    await expect(page.getByRole("button", { name: /새로고침/ }).first()).toBeVisible();
  });

  test("/admin/tables search filters the live table list", async ({ page }) => {
    await gotoAdmin(page, "/admin/tables", ADMIN_PAGES.tables.title);
    const table = page.getByRole("table", { name: "PostgreSQL 테이블 통계" });
    await expect(table).toBeVisible({ timeout: LIVE_TIMEOUT });
    await page.getByPlaceholder("테이블 검색").fill("mv_geocode");
    await expect(table.getByRole("cell", { name: /mv_geocode/ }).first()).toBeVisible({
      timeout: LIVE_TIMEOUT
    });
  });
});

test.describe("LIVE backups admin browser tabs", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdminPage(page, "/admin/backups");
  });

  test("backups overview tab renders the workflow guide", async ({ page }) => {
    await gotoAdmin(page, "/admin/backups", ADMIN_PAGES.backups.title);
    await expect(page.getByRole("tab", { name: "개요", selected: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "백업/복원 다음 액션" })).toBeVisible();
  });

  test("backups backup tab renders backup form and artifact table", async ({ page }) => {
    await gotoAdmin(page, "/admin/backups", ADMIN_PAGES.backups.title);
    await page.getByRole("tab", { name: "백업" }).click();
    await expect(page.getByRole("heading", { name: "DB Backup", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Backup Artifacts" })).toBeVisible();
  });

  test("backups backup tab exposes profile/jobs/compression fields", async ({ page }) => {
    await gotoAdmin(page, "/admin/backups", ADMIN_PAGES.backups.title);
    await page.getByRole("tab", { name: "백업" }).click();
    // "라벨 (api_field)" 병기는 "라벨" + HelpTip으로 이동 — exact:true로 HelpTip 접근명과 분리.
    await expect(page.getByLabel("백업 프로파일", { exact: true })).toBeVisible();
    await expect(page.getByLabel("병렬 작업 수", { exact: true })).toBeVisible();
    await expect(page.getByLabel("압축 레벨", { exact: true })).toBeVisible();
  });

  test("backups restore tab renders the restore wizard without executing it", async ({ page }) => {
    await gotoAdmin(page, "/admin/backups", ADMIN_PAGES.backups.title);
    await page.getByRole("tab", { name: "복원" }).click();
    await expect(page.getByRole("heading", { name: "복원 위저드" })).toBeVisible();
    await expect(page.getByText("1. 백업·모드 선택")).toBeVisible();
  });

  test("backups hot-swap tab renders the plan form without executing it", async ({ page }) => {
    await gotoAdmin(page, "/admin/backups", ADMIN_PAGES.backups.title);
    await page.getByRole("tab", { name: "Hot-swap" }).click();
    await expect(page.getByRole("heading", { name: /Hot-swap plan/ })).toBeVisible();
    await expect(page.getByLabel("복원된 DB 이름", { exact: true })).toBeVisible();
  });

  test("backups jobs tab renders the jobs table", async ({ page }) => {
    await gotoAdmin(page, "/admin/backups", ADMIN_PAGES.backups.title);
    await page.getByRole("tab", { name: "작업" }).click();
    await expect(page.getByRole("heading", { name: "Backup / Restore Jobs" })).toBeVisible();
    await expect(page.getByRole("table", { name: "백업/복원 작업 목록" })).toBeVisible();
  });
});

test.describe("LIVE source-files admin browser tabs", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdminPage(page, "/admin/source-files");
  });

  test("source-files renders all six tabs", async ({ page }) => {
    await gotoAdmin(page, "/admin/source-files", ADMIN_PAGES.sourceFiles.title);
    for (const name of ["업로드", "목록", "매칭 세트", "RustFS 정합성", "현재 구성", "검증 케이스"]) {
      await expect(page.getByRole("tab", { name })).toBeVisible();
    }
  });

  test("source-files upload tab renders category upload surface", async ({ page }) => {
    await gotoAdmin(page, "/admin/source-files", ADMIN_PAGES.sourceFiles.title);
    await expect(page.getByRole("heading", { name: "카테고리별 업로드" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "재개 가능한 업로드" })).toBeVisible();
  });

  test("source-files list tab renders capacity and group tables", async ({ page }) => {
    await gotoAdmin(page, "/admin/source-files", ADMIN_PAGES.sourceFiles.title);
    await page.getByRole("tab", { name: "목록" }).click();
    await expect(page.getByRole("heading", { name: "용량 / 이슈 요약" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "원천 파일 그룹" })).toBeVisible();
  });

  test("source-files match-set tab renders detail and compare surfaces", async ({ page }) => {
    await gotoAdmin(page, "/admin/source-files", ADMIN_PAGES.sourceFiles.title);
    await page.getByRole("tab", { name: "매칭 세트" }).click();
    await expect(page.getByRole("heading", { name: "매칭 세트", exact: true })).toBeVisible();
    await expect(page.getByText(/비교|세부 정보|DB 재구성/).first()).toBeVisible({
      timeout: LIVE_TIMEOUT
    });
  });

  test("source-files reconcile tab renders runs, issues, and capacity", async ({ page }) => {
    await gotoAdmin(page, "/admin/source-files", ADMIN_PAGES.sourceFiles.title);
    await page.getByRole("tab", { name: "RustFS 정합성" }).click();
    // "정합성 실행 (RustFS ⟷ DB)" → "정합성 실행" (+HelpTip). exact:true 필수 —
    // 같은 화면의 다른 heading과 substring 충돌 방지.
    await expect(page.getByRole("heading", { name: "정합성 실행", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "이슈 항목" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "용량", exact: true })).toBeVisible();
  });

  test("source-files current config tab renders serving configuration", async ({ page }) => {
    await gotoAdmin(page, "/admin/source-files", ADMIN_PAGES.sourceFiles.title);
    await page.getByRole("tab", { name: "현재 구성" }).click();
    await expect(page.getByRole("heading", { name: "현재 serving 구성" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "DB를 만든 원천 매칭 정보" })).toBeVisible();
  });

  test("source-files cases tab renders registry-backed validation cases", async ({ page }) => {
    await gotoAdmin(page, "/admin/source-files", ADMIN_PAGES.sourceFiles.title);
    await page.getByRole("tab", { name: "검증 케이스" }).click();
    await expect(page.getByRole("heading", { name: /검증 케이스/ })).toBeVisible();
    await expect(page.getByRole("tablist", { name: "검증 케이스" })).toBeVisible({
      timeout: LIVE_TIMEOUT
    });
  });
});

test.describe("LIVE ops and consistency browser panels", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdminPage(page, "/admin/ops");
  });

  test("ops renders serving release and snapshot tables", async ({ page }) => {
    await gotoAdmin(page, "/admin/ops", ADMIN_PAGES.ops.title);
    await expect(page.getByRole("table", { name: "서빙 릴리스 목록" })).toBeVisible();
    await expect(page.getByRole("table", { name: "데이터셋 스냅샷 목록" })).toBeVisible();
  });

  test("ops renders the maintenance window form and table", async ({ page }) => {
    await gotoAdmin(page, "/admin/ops", ADMIN_PAGES.ops.title);
    await expect(page.getByRole("heading", { name: "유지보수 윈도우" })).toBeVisible();
    // exact:true 필수 — HelpTip 버튼("작업 종류 도움말")과 substring 충돌 방지.
    await expect(page.getByLabel("작업 종류", { exact: true })).toBeVisible();
    await expect(page.getByRole("table", { name: "유지보수 윈도우 목록" })).toBeVisible();
  });

  test("ops renders table-stats snapshot panel", async ({ page }) => {
    await gotoAdmin(page, "/admin/ops", ADMIN_PAGES.ops.title);
    await expect(page.getByRole("heading", { name: "테이블 통계 스냅샷" })).toBeVisible();
    await expect(page.getByRole("table", { name: "테이블 통계 스냅샷 목록" })).toBeVisible();
  });

  test("ops renders pg_stat statements panel", async ({ page }) => {
    await gotoAdmin(page, "/admin/ops", ADMIN_PAGES.ops.title);
    await expect(page.getByRole("heading", { name: "쿼리 통계" })).toBeVisible();
    await expect(page.getByRole("table", { name: "pg_stat_statements 상위 쿼리 목록" })).toBeVisible();
  });

  test("ops renders artifacts and audit-event tables", async ({ page }) => {
    await gotoAdmin(page, "/admin/ops", ADMIN_PAGES.ops.title);
    await expect(page.getByRole("table", { name: "아티팩트 목록" })).toBeVisible();
    await expect(page.getByRole("table", { name: "감사 이벤트 목록" })).toBeVisible();
  });

  test("ops renders Last Response panel for partial-load diagnostics", async ({ page }) => {
    await gotoAdmin(page, "/admin/ops", ADMIN_PAGES.ops.title);
    await expect(page.getByRole("heading", { name: "최근 결과" })).toBeVisible();
    await expect(page.locator("pre.json-box").last()).toBeVisible();
  });

  test("consistency renders reports panel and workbench shell", async ({ page }) => {
    await gotoAdmin(page, "/admin/consistency", ADMIN_PAGES.consistency.title);
    await expect(page.getByRole("heading", { name: "Reports", exact: true })).toBeVisible();
    await expect(page.getByRole("tabpanel").first()).toBeVisible({ timeout: LIVE_TIMEOUT });
  });

  test("consistency exposes safe filtering controls when a case is selected", async ({ page }) => {
    await gotoAdmin(page, "/admin/consistency", ADMIN_PAGES.consistency.title);
    const severity = page.getByLabel("심각도 필터");
    const reports = page.getByRole("heading", { name: "Reports", exact: true });
    await expect(severity.or(reports).first()).toBeVisible({ timeout: LIVE_TIMEOUT });
    if (await severity.count()) {
      await expect(page.getByLabel("판정 필터")).toBeVisible();
      await expect(page.getByLabel("시군구코드 필터")).toBeVisible();
      await expect(page.getByLabel("정렬 기준")).toBeVisible();
    }
  });
});
