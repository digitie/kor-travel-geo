import { expect, test, type APIResponse } from "@playwright/test";

import { isLiveE2EEnabled, proxyGet } from "./_live";

// LIVE admin read-only query matrix.
//
// The Admin UI talks to the backend through the same-origin Next proxy. These tests exercise
// that proxy path with safe GET requests only, covering pagination/filter variants without
// assuming this live DB has rows for every operational table.

type Row = Record<string, unknown>;

type MatrixCase = {
  name: string;
  path: string;
  params?: Record<string, string | number | boolean>;
  limit?: number;
  allowUnavailable?: boolean;
  rowCheck?: (row: Row) => void;
};

async function readBody(res: APIResponse): Promise<unknown> {
  return res.json() as Promise<unknown>;
}

function expectArrayContract(body: unknown, item: MatrixCase): Row[] {
  expect(Array.isArray(body)).toBe(true);
  const rows = body as Row[];
  if (item.limit !== undefined) {
    expect(rows.length).toBeLessThanOrEqual(item.limit);
  }
  if (rows.length > 0) {
    item.rowCheck?.(rows[0]);
  }
  return rows;
}

const stringField = (field: string) => (row: Row) => {
  expect(typeof row[field]).toBe("string");
};

const matrix: MatrixCase[] = [
  { name: "tables limit 1", path: "v1/admin/tables", params: { limit: 1 }, limit: 1, rowCheck: stringField("table_name") },
  { name: "tables limit 2", path: "v1/admin/tables", params: { limit: 2 }, limit: 2, rowCheck: stringField("table_name") },
  { name: "tables limit 5", path: "v1/admin/tables", params: { limit: 5 }, limit: 5, rowCheck: stringField("table_name") },
  { name: "tables limit 20", path: "v1/admin/tables", params: { limit: 20 }, limit: 20, rowCheck: stringField("table_name") },
  { name: "logs limit 1", path: "v1/admin/logs", params: { limit: 1 }, limit: 1 },
  { name: "logs limit 5", path: "v1/admin/logs", params: { limit: 5 }, limit: 5 },
  { name: "logs limit 50", path: "v1/admin/logs", params: { limit: 50 }, limit: 50 },
  { name: "backups limit 1", path: "v1/admin/backups", params: { limit: 1 }, limit: 1, rowCheck: stringField("artifact_id") },
  { name: "backups available", path: "v1/admin/backups", params: { state: "available", limit: 5 }, limit: 5, rowCheck: stringField("artifact_id") },
  { name: "backups deleted", path: "v1/admin/backups", params: { state: "deleted", limit: 5 }, limit: 5, rowCheck: stringField("artifact_id") },
  { name: "backups expiring soon", path: "v1/admin/backups", params: { expiring_within_days: 30, limit: 5 }, limit: 5, rowCheck: stringField("artifact_id") },
  { name: "jobs limit 1", path: "v1/admin/jobs", params: { limit: 1 }, limit: 1, rowCheck: stringField("job_id") },
  { name: "jobs limit 5", path: "v1/admin/jobs", params: { limit: 5 }, limit: 5, rowCheck: stringField("job_id") },
  { name: "jobs done", path: "v1/admin/jobs", params: { state: "done", limit: 5 }, limit: 5, rowCheck: stringField("job_id") },
  { name: "jobs failed", path: "v1/admin/jobs", params: { state: "failed", limit: 5 }, limit: 5, rowCheck: stringField("job_id") },
  { name: "jobs db_backup", path: "v1/admin/jobs", params: { kind: "db_backup", limit: 5 }, limit: 5, rowCheck: stringField("job_id") },
  { name: "jobs db_restore", path: "v1/admin/jobs", params: { kind: "db_restore", limit: 5 }, limit: 5, rowCheck: stringField("job_id") },
  { name: "jobs source_rebuild_db", path: "v1/admin/jobs", params: { kind: "source_rebuild_db", limit: 5 }, limit: 5, rowCheck: stringField("job_id") },
  { name: "loads limit 3", path: "v1/admin/loads", params: { limit: 3 }, limit: 3, rowCheck: stringField("job_id") },
  { name: "loads running", path: "v1/admin/loads", params: { state: "running", limit: 5 }, limit: 5, rowCheck: stringField("job_id") },
  { name: "loads full_load_batch", path: "v1/admin/loads", params: { kind: "full_load_batch", limit: 5 }, limit: 5, rowCheck: stringField("job_id") },
  { name: "consistency limit 1", path: "v1/admin/consistency", params: { limit: 1 }, limit: 1, rowCheck: stringField("report_id") },
  { name: "consistency warn", path: "v1/admin/consistency", params: { severity_at_least: "WARN", limit: 5 }, limit: 5, rowCheck: stringField("report_id") },
  { name: "consistency error", path: "v1/admin/consistency", params: { severity_at_least: "ERROR", limit: 5 }, limit: 5, rowCheck: stringField("report_id") },
  { name: "audit limit 1", path: "v1/admin/ops/audit-events", params: { limit: 1 }, limit: 1, rowCheck: stringField("action") },
  { name: "audit outcome succeeded", path: "v1/admin/ops/audit-events", params: { outcome: "succeeded", limit: 5 }, limit: 5, rowCheck: stringField("action") },
  { name: "audit outcome failed", path: "v1/admin/ops/audit-events", params: { outcome: "failed", limit: 5 }, limit: 5, rowCheck: stringField("action") },
  { name: "snapshots limit 1", path: "v1/admin/ops/snapshots", params: { limit: 1 }, limit: 1, rowCheck: stringField("dataset_snapshot_id") },
  { name: "snapshots active", path: "v1/admin/ops/snapshots", params: { state: "active", limit: 5 }, limit: 5, rowCheck: stringField("dataset_snapshot_id") },
  { name: "releases limit 1", path: "v1/admin/ops/releases", params: { limit: 1 }, limit: 1, rowCheck: stringField("serving_release_id") },
  { name: "releases active", path: "v1/admin/ops/releases", params: { state: "active", limit: 5 }, limit: 5, rowCheck: stringField("serving_release_id") },
  { name: "releases retired", path: "v1/admin/ops/releases", params: { state: "retired", limit: 5 }, limit: 5, rowCheck: stringField("serving_release_id") },
  { name: "artifacts limit 1", path: "v1/admin/ops/artifacts", params: { limit: 1 }, limit: 1, rowCheck: stringField("artifact_id") },
  { name: "artifacts db_backup", path: "v1/admin/ops/artifacts", params: { artifact_type: "db_backup", limit: 5 }, limit: 5, rowCheck: stringField("artifact_id") },
  { name: "artifacts benchmark", path: "v1/admin/ops/artifacts", params: { artifact_type: "benchmark", limit: 5 }, limit: 5, rowCheck: stringField("artifact_id") },
  { name: "artifacts available", path: "v1/admin/ops/artifacts", params: { state: "available", limit: 5 }, limit: 5, rowCheck: stringField("artifact_id") },
  { name: "maintenance limit 1", path: "v1/admin/ops/maintenance-windows", params: { limit: 1 }, limit: 1, rowCheck: stringField("maintenance_window_id") },
  { name: "maintenance open", path: "v1/admin/ops/maintenance-windows", params: { state: "open", limit: 5 }, limit: 5, rowCheck: stringField("maintenance_window_id") },
  { name: "maintenance ended", path: "v1/admin/ops/maintenance-windows", params: { state: "ended", limit: 5 }, limit: 5, rowCheck: stringField("maintenance_window_id") },
  { name: "table stats limit 1", path: "v1/admin/ops/table-stats", params: { limit: 1 }, limit: 1, rowCheck: stringField("schema_name") },
  { name: "table stats limit 5", path: "v1/admin/ops/table-stats", params: { limit: 5 }, limit: 5, rowCheck: stringField("schema_name") },
  { name: "pg stat latest limit 1", path: "v1/admin/ops/pg-stat-statements", params: { latest_only: true, limit: 1 }, limit: 1, allowUnavailable: true },
  { name: "pg stat all limit 3", path: "v1/admin/ops/pg-stat-statements", params: { latest_only: false, limit: 3 }, limit: 3, allowUnavailable: true }
];

test.describe("LIVE admin API query matrix", () => {
  test.beforeEach(() => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
  });

  for (const item of matrix) {
    test(item.name, async ({ request }) => {
      const res = await proxyGet(request, item.path, item.params);
      if (item.allowUnavailable) {
        expect([200, 503]).toContain(res.status());
      } else {
        expect(res.status()).toBe(200);
      }
      const body = await readBody(res);
      if (res.status() === 200) {
        const rows = expectArrayContract(body, item);
        if (item.params?.state && rows.length > 0) {
          expect(rows.every((row) => row.state === item.params?.state)).toBe(true);
        }
      } else {
        expect(Array.isArray(body)).toBe(false);
      }
    });
  }

  test("cache metrics exposes all numeric counters", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/cache/metrics");
    expect(res.status()).toBe(200);
    const body = (await readBody(res)) as Row;
    for (const field of ["entries", "hits", "expired"]) {
      expect(typeof body[field]).toBe("number");
    }
  });

  test("backup allowed dirs exposes default dir only when dirs are present", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/backups/allowed-dirs");
    expect(res.status()).toBe(200);
    const body = (await readBody(res)) as Row;
    expect(Array.isArray(body.dirs)).toBe(true);
    if ((body.dirs as unknown[]).length > 0) {
      expect(typeof body.default_dir).toBe("string");
    }
  });

  test("source category catalog has stable category records", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/source-file-categories");
    expect(res.status()).toBe(200);
    const body = (await readBody(res)) as { categories?: Row[] };
    expect(Array.isArray(body.categories)).toBe(true);
    expect(body.categories!.length).toBeGreaterThan(0);
    expect(body.categories!.every((row) => typeof row.category === "string")).toBe(true);
  });

  test("source category catalog includes serving usage and member-kind metadata", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/source-file-categories");
    expect(res.status()).toBe(200);
    const body = (await readBody(res)) as { categories?: Row[] };
    const categories = body.categories ?? [];
    expect(categories.some((row) => typeof row.serving_usage === "string")).toBe(true);
    expect(categories.some((row) => typeof row.label === "string")).toBe(true);
    expect(categories.some((row) => Array.isArray(row.expected_member_kinds))).toBe(true);
  });

  test("consistency registry contains code/name/severity metadata", async ({ request }) => {
    const res = await proxyGet(request, "v1/admin/consistency/case-definitions");
    expect(res.status()).toBe(200);
    const rows = (await readBody(res)) as Row[];
    expect(Array.isArray(rows)).toBe(true);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((row) => typeof row.code === "string" && typeof row.name === "string")).toBe(true);
  });
});
