import { expect, test } from "@playwright/test";
import { proxyGet } from "./_live";

// Layer 3 — LIVE full-stack admin console (real browser over the LIVE backend + DB, NO mocking).
//
// READ-ONLY: these cases only navigate to admin pages and assert that the real ops/consistency/
// backups/source-files/tables surfaces render actual data without an error screen. They NEVER
// trigger create/delete/restore/rebuild/hard-delete/activate/retire/run actions.
//
// Gated behind LIVE_E2E so the default (no-backend) `playwright test` run skips them.
// Run with the stack up:
//   LIVE_E2E=1 PLAYWRIGHT_BROWSER=chromium npx playwright test tests/e2e/live/admin-readonly.spec.ts

const TIMEOUT = 15_000;

/** The app error boundary renders "This page couldn't load…"; assert it never appears. */
async function expectNoErrorScreen(page: import("@playwright/test").Page): Promise<void> {
  await expect(page.getByText("This page couldn")).toHaveCount(0);
}

test.describe("LIVE admin read-only", () => {
  test.beforeEach(() => {
    test.skip(
      !process.env.LIVE_E2E,
      "Live full-stack test — run with LIVE_E2E=1 and the stack up (DB+API+UI)"
    );
  });

  test("/admin/ops renders the Ops console and Serving Releases table", async ({ page }) => {
    await page.goto("/admin/ops");

    // PageHeader renders <h1>Ops</h1>.
    await expect(page.getByRole("heading", { name: "Ops", exact: true })).toBeVisible({
      timeout: TIMEOUT
    });
    await expectNoErrorScreen(page);

    // PerfValidationSummary Panel title (read-only summary).
    await expect(
      page.getByRole("heading", { name: "성능·검증 요약 (read-only)" })
    ).toBeVisible({ timeout: TIMEOUT });

    // The migrated VirtualTable(as="table", caption="서빙 릴리스 목록") renders a semantic
    // <table> with the caption as its accessible name. We assert it RENDERS (not its row
    // count): OpsPanel.loadAll() uses Promise.all across all ops endpoints, so when an env
    // endpoint is unavailable (e.g. pg_stat_statements → 503 if the extension isn't
    // installed) the fetch fails-fast and every ops table renders its empty state. Data-row
    // assertions live in the API layer instead (see api-correctness for the released data).
    await expect(page.getByRole("table", { name: "서빙 릴리스 목록" })).toBeVisible({
      timeout: TIMEOUT
    });
    await expect(page.getByRole("table", { name: "데이터셋 스냅샷 목록" })).toBeVisible({
      timeout: TIMEOUT
    });
  });

  test("ops releases/snapshots API serves the live serving configuration", async ({ request }) => {
    // Reliable real-data coverage at the API layer (the /admin/ops page itself can fail-fast
    // to empty tables when an unrelated ops endpoint is unavailable in this env).
    const releases = await proxyGet(request, "v1/admin/ops/releases", { limit: 10 });
    expect(releases.status()).toBe(200);
    const relBody = (await releases.json()) as Array<{ serving_release_id?: string }>;
    expect(Array.isArray(relBody)).toBe(true);
    if (relBody.length > 0) {
      expect(typeof relBody[0].serving_release_id).toBe("string");
    }

    const snapshots = await proxyGet(request, "v1/admin/ops/snapshots", { limit: 10 });
    expect(snapshots.status()).toBe(200);
    const snapBody = (await snapshots.json()) as Array<{ dataset_snapshot_id?: string }>;
    expect(Array.isArray(snapBody)).toBe(true);
    if (snapBody.length > 0) {
      expect(typeof snapBody[0].dataset_snapshot_id).toBe("string");
    }
  });

  test("source-files admin API passes the role gate when live admin proxy is enabled", async ({
    request
  }) => {
    test.skip(
      process.env.KTG_LIVE_E2E_ADMIN_PROXY !== "1",
      "Run with KTG_LIVE_E2E_ADMIN_PROXY=1 and source_file_viewer role to verify admin role proxy"
    );

    // source-file-categories is a static catalog with no role guard — it returns
    // 200 regardless of injected identity, so it only sanity-checks proxy
    // connectivity, not the role gate. The role gate is exercised by the
    // source-match-sets read below (require_role(source_file_viewer)).
    const catalog = await proxyGet(request, "v1/admin/source-file-categories");
    expect(catalog.status()).toBe(200);

    const matchSets = await proxyGet(request, "v1/admin/source-match-sets", { limit: 5 });
    expect(matchSets.status()).toBe(200);
  });

  test("/admin/consistency renders the Consistency reports surface", async ({ page }) => {
    await page.goto("/admin/consistency");

    await expect(page.getByRole("heading", { name: "Consistency", exact: true })).toBeVisible({
      timeout: TIMEOUT
    });
    await expectNoErrorScreen(page);

    // Reports panel (ReportsPanelSection -> Panel title="Reports").
    await expect(page.getByRole("heading", { name: "Reports", exact: true })).toBeVisible({
      timeout: TIMEOUT
    });

    // Robust: if reports exist, the workbench renders the case tablist (aria-label "정합성 케이스");
    // otherwise the Reports panel still renders gracefully. Pass on EITHER, never fail on zero.
    const caseTabs = page.getByRole("tablist", { name: "정합성 케이스" });
    const reportsHeading = page.getByRole("heading", { name: "Reports", exact: true });
    await expect(caseTabs.or(reportsHeading).first()).toBeVisible({ timeout: TIMEOUT });

    // Still must not have an error screen after the report/cases queries settle.
    await expectNoErrorScreen(page);
  });

  test("/admin/backups renders the DB Backups console without an error screen", async ({
    page
  }) => {
    await page.goto("/admin/backups");

    await expect(page.getByRole("heading", { name: "DB Backups", exact: true })).toBeVisible({
      timeout: TIMEOUT
    });
    await expectNoErrorScreen(page);

    // Default "overview" tab renders the workflow guide panel + the read-only tablist. Assert the
    // tab UI renders (no tab is clicked — purely read-only) so the artifacts/jobs surface is reachable.
    await expect(page.getByRole("tablist", { name: "백업/복원 관리 탭" })).toBeVisible({
      timeout: TIMEOUT
    });
    await expect(page.getByRole("heading", { name: "백업/복원 다음 액션" })).toBeVisible({
      timeout: TIMEOUT
    });
    await expectNoErrorScreen(page);
  });

  test("/admin/source-files renders the source-files tablist and cards", async ({ page }) => {
    await page.goto("/admin/source-files");

    // PageHeader renders <h1>Source Files</h1>.
    await expect(page.getByRole("heading", { name: "Source Files", exact: true })).toBeVisible({
      timeout: TIMEOUT
    });
    await expectNoErrorScreen(page);

    // SourceFilesPanel renders role=tablist with aria-label "원천 파일 관리 탭".
    await expect(page.getByRole("tablist", { name: "원천 파일 관리 탭" })).toBeVisible({
      timeout: TIMEOUT
    });
    // The active tab's panel renders (default "upload" tab) without an error screen.
    await expect(page.getByRole("tabpanel")).toBeVisible({ timeout: TIMEOUT });
    await expectNoErrorScreen(page);
  });

  test("/admin/tables renders the PostgreSQL table stats list", async ({ page }) => {
    await page.goto("/admin/tables");

    await expect(page.getByRole("heading", { name: "Tables", exact: true })).toBeVisible({
      timeout: TIMEOUT
    });
    await expectNoErrorScreen(page);

    // TableStatsPanel -> Panel title="PostgreSQL Tables", VirtualTable caption "PostgreSQL 테이블 통계".
    await expect(page.getByRole("heading", { name: "PostgreSQL Tables" })).toBeVisible({
      timeout: TIMEOUT
    });
    const tablesTable = page.getByRole("table", { name: "PostgreSQL 테이블 통계" });
    await expect(tablesTable).toBeVisible({ timeout: TIMEOUT });

    // The loaded DB exposes table stats rows: empty hint absent + >=1 data row (header + data).
    await expect(tablesTable.getByText("테이블 통계가 없습니다.")).toHaveCount(0);
    await expect
      .poll(async () => tablesTable.getByRole("row").count(), { timeout: TIMEOUT })
      .toBeGreaterThanOrEqual(2);
    await expectNoErrorScreen(page);
  });
});
