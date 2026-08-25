import { expect, test } from "@playwright/test";
import { LIVE_TIMEOUT, loginLiveAdminPage, proxyGet } from "./_live";

// Layer 2 — issue #523: `ops.table_stats_snapshots.estimated_rows` recorded "never analyzed"
// (`pg_class.reltuples = -1`) as `0 rows`. On a live read a 0 is a defensible fallback; in a
// history row it is a lie you cannot tell apart afterwards.
//
// This spec WRITES: it triggers one capture, which appends a snapshot set to the ops history.
// That is the endpoint's own purpose and the table is not append-only-triggered, but it is a
// mutation — hence the explicit opt-in below, matching the convention used by the public-api-key
// mutation spec.

type Snapshot = {
  object_name: string;
  object_kind: string;
  estimated_rows?: number | null;
  dead_tuples?: number | null;
  stats?: Record<string, unknown>;
};

test.describe("LIVE ops table-stats capture (#523)", () => {
  test("미분석 관계를 0행이 아니라 NULL로 기록한다", async ({ page }) => {
    test.skip(!process.env.LIVE_E2E, "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    test.skip(
      process.env.KTG_LIVE_E2E_MUTATE_OPS_SNAPSHOTS !== "1",
      "Appends a snapshot set to ops history; set KTG_LIVE_E2E_MUTATE_OPS_SNAPSHOTS=1"
    );
    await loginLiveAdminPage(page, "/admin");

    const captured = await page.request.post(
      "/api/proxy/v1/admin/ops/table-stats/capture?limit=2000",
      { timeout: LIVE_TIMEOUT * 4 }
    );
    expect(captured.status()).toBe(200);
    const rows = (await captured.json()) as Snapshot[];
    expect(rows.length).toBeGreaterThan(0);

    // Provenance must be present on every row — it is what lets a future trend chart tell a
    // formula change from a data change. Rows written before #523 lack the key entirely.
    for (const row of rows) {
      expect(
        row.stats?.estimated_rows_source,
        `${row.object_name} has no estimated_rows_source`
      ).toBeTruthy();
    }

    // Indexes have no row count of their own: `reltuples` there counts index ENTRIES.
    // `response_model_exclude_none=True` omits the field entirely rather than sending null.
    const indexes = rows.filter((r) => r.object_kind === "index");
    expect(indexes.length).toBeGreaterThan(0);
    for (const row of indexes) {
      expect(row.estimated_rows ?? null, `index ${row.object_name} reported a row count`).toBeNull();
      expect(row.stats?.estimated_rows_source).toBe("not_applicable");
      // Same defect class (issue #525): an index has no `pg_stat_user_tables` row, so a
      // dead-tuple count of 0 was being fabricated into a permanent history row.
      expect(
        row.dead_tuples ?? null,
        `index ${row.object_name} reported a fabricated dead_tuples`
      ).toBeNull();
    }

    // The headline fix: no relation may claim an exact-looking 0 while its statistics are
    // unanchored. Before #523 every never-analyzed relation reported exactly that.
    const zeroButUnanchored = rows.filter(
      (r) =>
        r.estimated_rows === 0 &&
        r.stats?.estimated_rows_source !== "live_tuples_anchored" &&
        r.stats?.estimated_rows_source !== "not_applicable"
    );
    expect(
      zeroButUnanchored.map((r) => r.object_name),
      "unanchored relations must record NULL, not 0"
    ).toEqual([]);

    // A loaded serving database must have anchored counts for its materialized views.
    const anchored = rows.filter((r) => r.stats?.estimated_rows_source === "live_tuples_anchored");
    expect(anchored.length, "expected at least one anchored relation on a loaded DB").toBeGreaterThan(0);

    // And the persisted history must read back the same way.
    const listed = await proxyGet(page.request, "v1/admin/ops/table-stats", { limit: 1000 });
    expect(listed.status()).toBe(200);
    const stored = (await listed.json()) as Snapshot[];
    expect(stored.length).toBeGreaterThan(0);
    for (const row of stored) {
      expect(row.estimated_rows == null || row.estimated_rows >= 0).toBe(true);
    }
  });
});
