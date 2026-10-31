import { expect, test } from "@playwright/test";
import { LIVE_TIMEOUT, loginLiveAdminPage, proxyGet } from "./_live";

// Layer 2 — issue #515 core symptom: `/admin/tables` reported 0 (or a handful) of rows for
// tables holding millions, because `n_live_tup` is a statistics-collector DELTA that a restore
// or hot-swap resets. On this box the nationwide dataset is loaded, so a 0 here is a real defect
// and not an empty database.
//
// Asserted against the API AND the rendered table, because two of the three bad versions of
// this query produced a plausible-looking number that was simply wrong rather than an error.

/** Loaded by the nationwide pipeline; the MV is analyzed on every swap, so it is never empty. */
const POPULATED_TABLE = "mv_geocode_target";

test.describe("LIVE /admin/tables 행 수 (#515)", () => {
  test("적재된 테이블이 0으로 표시되지 않는다", async ({ page }) => {
    test.skip(!process.env.LIVE_E2E, "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdminPage(page, "/admin");

    const response = await proxyGet(page.request, "v1/admin/tables", { limit: 500 });
    expect(response.status()).toBe(200);
    const rows = (await response.json()) as {
      table_name: string;
      row_count: number;
      row_count_estimated?: boolean;
    }[];
    expect(rows.length).toBeGreaterThan(0);

    const populated = rows.find((r) => r.table_name === POPULATED_TABLE);
    expect(populated, `${POPULATED_TABLE} missing from /admin/tables`).toBeTruthy();
    // The reported symptom was 0 / 6 for a table with hundreds of thousands of rows.
    expect(populated!.row_count).toBeGreaterThan(1000);

    // No row may be negative — `n_live_tup` can go negative on a reset and `reltuples` is -1
    // until something analyzes the relation.
    for (const row of rows) {
      expect(row.row_count, `${row.table_name} row_count`).toBeGreaterThanOrEqual(0);
    }
    // 이 플래그는 통계 기준 유무다. false여도 통계 행 수가 확정치가 되는 것은 아니다.
    expect(typeof populated!.row_count_estimated).toBe("boolean");
  });

  test("분석 이력이 있어도 추정치와 갱신 시각의 의미를 표시한다", async ({ page }) => {
    test.skip(!process.env.LIVE_E2E, "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdminPage(page, "/admin");

    const response = await proxyGet(page.request, "v1/admin/tables", { limit: 500 });
    const rows = (await response.json()) as {
      table_name: string;
      row_count: number;
      row_count_estimated?: boolean;
    }[];

    await page.goto("/admin/tables", { waitUntil: "networkidle" });
    await expect(page.getByRole("table", { name: "PostgreSQL 테이블 통계" })).toBeVisible({
      timeout: LIVE_TIMEOUT
    });

    const legend = page.getByText("표시된 행 수는 통계 기반 추정치입니다", {
      exact: false
    });
    await expect(legend).toHaveCount(rows.length > 0 ? 1 : 0);

    // The populated table's rendered count must match the API, digit-grouped.
    const populated = rows.find((r) => r.table_name === POPULATED_TABLE)!;
    await page.getByPlaceholder("테이블 검색").fill(POPULATED_TABLE);
    const row = page.getByRole("row").filter({ hasText: POPULATED_TABLE }).first();
    await expect(row).toContainText(populated.row_count.toLocaleString(), {
      timeout: LIVE_TIMEOUT
    });
    await expect(row).toContainText("≈");
    await expect(page.getByRole("columnheader", { name: "통계 갱신" })).toBeVisible();
  });
});
