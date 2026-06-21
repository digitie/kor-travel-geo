import { expect, test } from "@playwright/test";

import {
  hasLiveAdminProxyRole,
  isLiveE2EEnabled,
  proxyGet
} from "./_live";

// LIVE admin API read-only contract tests.
//
// These use the same-origin UI proxy against the real backend + DB. They intentionally avoid
// POST/PATCH/DELETE and do not trigger backup, restore, rebuild, reconcile, validation, or
// hard-delete actions.

type Row = Record<string, unknown>;

const SOURCE_ROLE_HINT =
  "Run with KTG_LIVE_E2E_ADMIN_PROXY=1 and source_file_viewer role for source-file admin reads";

test.describe("LIVE admin API read-only contracts", () => {
  test.beforeEach(() => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
  });

  test("runtime config endpoint returns a JSON object", async ({ request }) => {
    const res = await request.get("/api/runtime-config");
    expect(res.status()).toBe(200);
    const body = (await res.json()) as Row;
    expect(body).toHaveProperty("vworldApiKey");
  });

  test("admin tables returns table stats rows", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/tables", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
    expect(rows.length).toBeGreaterThan(0);
    expect(typeof rows[0].table_name).toBe("string");
    expect(typeof rows[0].row_count).toBe("number");
  });

  test("admin tables respects small limit", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/tables", { limit: 3 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(rows.length).toBeLessThanOrEqual(3);
  });

  test("admin cache metrics returns numeric counters", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/cache/metrics");
    expect(res.status()).toBe(200);
    const body = (await res.json()) as Row;
    expect(typeof body.entries).toBe("number");
    expect(typeof body.hits).toBe("number");
    expect(typeof body.expired).toBe("number");
  });

  test("admin logs returns a bounded string array", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/logs", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as unknown[];
    expect(Array.isArray(rows)).toBe(true);
    expect(rows.length).toBeLessThanOrEqual(20);
    expect(rows.every((line) => typeof line === "string")).toBe(true);
  });

  test("backup allowed dirs endpoint returns dirs", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/backups/allowed-dirs");
    expect(res.status()).toBe(200);
    const body = (await res.json()) as { dirs?: unknown };
    expect(Array.isArray(body.dirs)).toBe(true);
  });

  test("backup artifact list is readable", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/backups", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
    if (rows.length > 0) {
      expect(typeof rows[0].artifact_id).toBe("string");
      expect(rows[0].artifact_type).toBe("db_backup");
    }
  });

  test("admin jobs list is readable", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/jobs", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
    if (rows.length > 0) {
      expect(typeof rows[0].job_id).toBe("string");
      expect(typeof rows[0].kind).toBe("string");
    }
  });

  test("admin jobs kind filter returns only db_backup rows when present", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/jobs", { kind: "db_backup", limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(rows.every((row) => row.kind === "db_backup")).toBe(true);
  });

  test("ops releases endpoint returns release rows", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/ops/releases", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
    if (rows.length > 0) {
      expect(typeof rows[0].serving_release_id).toBe("string");
    }
  });

  test("ops active release filter is readable", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/ops/releases", { state: "active", limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(rows.every((row) => row.state === "active")).toBe(true);
  });

  test("ops snapshots endpoint returns snapshot rows", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/ops/snapshots", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
    if (rows.length > 0) {
      expect(typeof rows[0].dataset_snapshot_id).toBe("string");
    }
  });

  test("ops artifacts endpoint is readable", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/ops/artifacts", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
  });

  test("ops artifacts can be filtered to db_backup", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/ops/artifacts", {
      artifact_type: "db_backup",
      limit: 20
    });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(rows.every((row) => row.artifact_type === "db_backup")).toBe(true);
  });

  test("ops audit event list is readable", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/ops/audit-events", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
    if (rows.length > 0) {
      expect(typeof rows[0].action).toBe("string");
      expect(typeof rows[0].outcome).toBe("string");
    }
  });

  test("ops maintenance windows endpoint is readable", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/ops/maintenance-windows", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
  });

  test("ops table-stats snapshots endpoint is readable", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/ops/table-stats", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
    if (rows.length > 0) {
      expect(typeof rows[0].schema_name).toBe("string");
      expect(typeof rows[0].object_name).toBe("string");
    }
  });

  test("ops pg-stat-statements endpoint either serves rows or structured unavailability", async ({
    request
  }) => {
    const res = await proxyGet(request, "v1/admin/ops/pg-stat-statements", { limit: 20 });
    expect([200, 503]).toContain(res.status());
    const body = (await res.json()) as Row[] | Row;
    if (res.status() === 200) {
      expect(Array.isArray(body)).toBe(true);
    } else {
      expect(Array.isArray(body)).toBe(false);
    }
  });

  test("consistency report list is readable", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/consistency");
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
  });

  test("consistency case registry includes named cases", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/consistency/case-definitions");
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
    expect(rows.length).toBeGreaterThanOrEqual(10);
    expect(rows.some((row) => row.code === "C1")).toBe(true);
  });

  test("latest consistency report detail is readable when a report exists", async ({ request }) => {
    const reports = await proxyGet(request, "v1/admin/consistency");
    expect(reports.status()).toBe(200);
    const reportRows = (await reports.json()) as Row[];
    test.skip(reportRows.length === 0, "No live consistency reports are registered in this DB");

    const reportId = String(reportRows[0].report_id);
    const detail = await proxyGet(request, `v1/admin/consistency/${reportId}`);
    expect(detail.status()).toBe(200);
    const body = (await detail.json()) as { cases?: Row[] };
    expect(Array.isArray(body.cases)).toBe(true);
  });

  test("latest consistency sample page is readable when report/case data exists", async ({
    request
  }) => {
    const reports = await proxyGet(request, "v1/admin/consistency");
    expect(reports.status()).toBe(200);
    const reportRows = (await reports.json()) as Row[];
    test.skip(reportRows.length === 0, "No live consistency reports are registered in this DB");

    const reportId = String(reportRows[0].report_id);
    const detail = await proxyGet(request, `v1/admin/consistency/${reportId}`);
    expect(detail.status()).toBe(200);
    const body = (await detail.json()) as { cases?: Row[] };
    const caseCode = body.cases?.[0]?.code;
    test.skip(typeof caseCode !== "string", "Latest consistency report has no cases");

    const samples = await proxyGet(
      request,
      `v1/admin/consistency/${reportId}/cases/${caseCode}/samples`,
      { page: 1, page_size: 5 }
    );
    expect(samples.status()).toBe(200);
    const sampleBody = (await samples.json()) as { items?: unknown[]; total?: number };
    expect(Array.isArray(sampleBody.items)).toBe(true);
    expect(typeof sampleBody.total).toBe("number");
  });

  test("source-file category catalog is readable without mutating state", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/source-file-categories");
    expect(res.status()).toBe(200);
    const body = (await res.json()) as { categories?: Row[] };
    expect(Array.isArray(body.categories)).toBe(true);
    expect(body.categories!.length).toBeGreaterThan(0);
  });

  test("source-file category catalog carries serving usage classifications", async ({
    request
  }) => {
    const res = await proxyGet(request, "v1/admin/source-file-categories");
    expect(res.status()).toBe(200);
    const body = (await res.json()) as { categories?: Row[] };
    const categories = body.categories ?? [];
    expect(categories.some((row) => typeof row.serving_usage === "string")).toBe(true);
  });
});

test.describe("LIVE source-files admin API read-only contracts", () => {
  test.beforeEach(() => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    test.skip(!hasLiveAdminProxyRole("source_file_viewer"), SOURCE_ROLE_HINT);
  });

  test("source match-set list passes the live role gate", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/source-match-sets", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
  });

  test("source match-set detail is readable when a match set exists", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/source-match-sets", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    test.skip(rows.length === 0, "No live source match sets are registered");

    const id = String(rows[0].source_match_set_id);
    const detail = await proxyGet(request, `v1/admin/source-match-sets/${id}`);
    expect(detail.status()).toBe(200);
    const body = (await detail.json()) as { match_set?: Row; items?: unknown[] };
    expect(body.match_set?.source_match_set_id).toBe(id);
    expect(Array.isArray(body.items)).toBe(true);
  });

  test("source capacity endpoint is readable", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/source-files/capacity");
    expect(res.status()).toBe(200);
    const body = (await res.json()) as Row;
    expect(typeof body.total_bytes).toBe("number");
    expect(typeof body.total_object_count).toBe("number");
  });

  test("source reconcile run list is readable", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/source-files/reconcile", { limit: 20 });
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
  });

  test("source reconcile item page is readable when a run exists", async ({ request }) => {
    const runs = await proxyGet(request, "v1/admin/source-files/reconcile", { limit: 20 });
    expect(runs.status()).toBe(200);
    const runRows = (await runs.json()) as Row[];
    test.skip(runRows.length === 0, "No live source reconcile runs are registered");

    const id = String(runRows[0].source_storage_reconcile_run_id);
    const items = await proxyGet(request, `v1/admin/source-files/reconcile/${id}/items`);
    expect(items.status()).toBe(200);
    const body = (await items.json()) as { items?: unknown[] };
    expect(Array.isArray(body.items)).toBe(true);
  });

  test("upload-session list is readable", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/source-files/upload-sessions");
    expect(res.status()).toBe(200);
    const rows = (await res.json()) as Row[];
    expect(Array.isArray(rows)).toBe(true);
  });
});
