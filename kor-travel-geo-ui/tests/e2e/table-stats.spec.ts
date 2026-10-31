import { expect, test } from "@playwright/test";

for (const flag of [false, true, undefined]) {
  test(`통계 기준 플래그 ${String(flag)}도 추정 행 수로 안내한다`, async ({ page }, testInfo) => {
    const mutations: string[] = [];
    await page.route("**/api/runtime-config", async (route) => {
      await route.fulfill({ json: { vworldApiKey: "" } });
    });
    await page.route("**/api/proxy/v1/admin/**", async (route) => {
      const request = route.request();
      if (!["GET", "HEAD"].includes(request.method())) mutations.push(request.url());
      const rows = new URL(request.url()).pathname.endsWith("/admin/tables") ? [{
        table_name: "tl_juso_text",
        row_count: 6_424_765,
        row_count_estimated: flag,
        size_bytes: 1000,
        updated_at: "2026-10-31 10:00:00+00"
      }] : [];
      await route.fulfill({ json: rows });
    });
    await page.goto("/admin/tables");
    await expect(page.getByRole("table", { name: "PostgreSQL 테이블 통계" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "추정 행 수" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "통계 갱신" })).toBeVisible();
    const row = page.getByRole("row").filter({ hasText: "tl_juso_text" });
    await expect(row).toContainText("6,424,765");
    await expect(row).toContainText("≈");
    await expect(page.getByText(/통계 갱신 시각은 적재 완료 시각이 아닙니다/)).toBeVisible();
    expect(mutations).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath("table-stats-estimates.png") });
  });
}
