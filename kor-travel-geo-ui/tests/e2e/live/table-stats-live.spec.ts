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
    // Whatever the count, the API must say whether it is a guess.
    expect(typeof populated!.row_count_estimated).toBe("boolean");
  });

  test("추정치 표시가 API 플래그와 일치하고 범례가 함께 뜬다", async ({ page }) => {
    test.skip(!process.env.LIVE_E2E, "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdminPage(page, "/admin");

    const response = await proxyGet(page.request, "v1/admin/tables", { limit: 500 });
    const rows = (await response.json()) as {
      table_name: string;
      row_count: number;
      row_count_estimated?: boolean;
    }[];
    const anyEstimated = rows.some((r) => r.row_count_estimated);

    await page.goto("/admin/tables", { waitUntil: "networkidle" });
    await expect(page.getByRole("table", { name: "PostgreSQL 테이블 통계" })).toBeVisible({
      timeout: LIVE_TIMEOUT
    });

    // The legend explains `≈` for sighted touch users (title tooltips never surface there), and
    // must appear exactly when at least one row is actually an estimate.
    const legend = page.getByText("표시는 해당 테이블에 vacuum/analyze 기록이 없어", {
      exact: false
    });
    await expect(legend).toHaveCount(anyEstimated ? 1 : 0);

    // The populated table's rendered count must match the API, digit-grouped.
    const populated = rows.find((r) => r.table_name === POPULATED_TABLE)!;
    await page.getByPlaceholder("테이블 검색").fill(POPULATED_TABLE);
    const row = page.getByRole("row").filter({ hasText: POPULATED_TABLE }).first();
    await expect(row).toContainText(populated.row_count.toLocaleString(), {
      timeout: LIVE_TIMEOUT
    });
    // `≈` shows on estimated rows only.
    await expect(row).toContainText(populated.row_count_estimated ? "≈" : populated.row_count.toLocaleString());
  });
});
