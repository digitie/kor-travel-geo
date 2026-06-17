import { expect, test, type Page } from "@playwright/test";

// /admin/ops 운영 콘솔의 7개 테이블(T-271 VirtualTable semantic 전환) 기능 e2e. ops-a11y.spec.ts는
// 회복성/키보드만 검증하고 ops 테이블 엔드포인트를 빈 배열로 두므로, 여기서는 각 테이블이 데이터를
// 행/셀로 렌더하고 semantic <table>(caption + <th scope=col>)으로 접근 가능한지 백엔드 없이 고정한다.

const RELEASES = [
  {
    serving_release_id: "rel-1",
    state: "active",
    release_kind: "full",
    mv_name: "mv_geocode_target",
    dataset_snapshot_id: "snap-1",
    activated_at: "2026-06-16T00:00:00Z",
    created_at: "2026-06-16T00:00:00Z"
  }
];
const SNAPSHOTS = [
  {
    dataset_snapshot_id: "snap-1",
    state: "ready",
    row_counts: { mv_geocode_target: 6_419_795, mv_geocode_text_search: 6_419_795 },
    created_at: "2026-06-16T00:00:00Z"
  }
];
const WINDOWS = [
  {
    maintenance_window_id: "win-1",
    kind: "full_load",
    state: "open",
    reason: "전국 재적재 운영 점검",
    created_at: "2026-06-16T00:00:00Z"
  }
];
const TABLE_STATS = [
  {
    table_stats_snapshot_id: "ts-1",
    schema_name: "public",
    object_name: "mv_geocode_target",
    object_kind: "matview",
    estimated_rows: 6_419_795,
    total_bytes: 1_234_567_890,
    captured_at: "2026-06-16T00:00:00Z"
  }
];
const PG_STATS = [
  {
    pg_stat_snapshot_id: "pg-1",
    rank: 1,
    operation: "SELECT",
    calls: 12_345,
    total_exec_time_ms: 9_876.5,
    mean_exec_time_ms: 0.8,
    query_preview: "SELECT * FROM mv_geocode_target WHERE bd_mgt_sn = $1",
    captured_at: "2026-06-16T00:00:00Z"
  }
];
const OPS_ARTIFACTS = [
  {
    artifact_id: "art-ops-1",
    artifact_type: "consistency_report",
    state: "available",
    storage_kind: "local_file",
    size_bytes: 4_096,
    created_at: "2026-06-16T00:00:00Z"
  }
];
const AUDIT_EVENTS = [
  {
    audit_event_id: "aud-1",
    occurred_at: "2026-06-16T00:00:00Z",
    action: "maintenance_window.open",
    outcome: "success"
  }
];

function jsonRoute(body: unknown) {
  return { contentType: "application/json", body: JSON.stringify(body) };
}

type Opts = { releases?: unknown[] };

async function mockOpsApi(page: Page, opts: Opts = {}): Promise<void> {
  const releases = opts.releases ?? RELEASES;
  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill(jsonRoute({ vworldApiKey: "" }));
  });
  await page.route("**/api/proxy/v1/admin/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;

    if (pathname.endsWith("/ops/artifacts")) {
      // PerfValidationSummary는 benchmark만, OpsPanel Artifacts 표는 전체를 조회한다.
      const isBenchmark = url.searchParams.get("artifact_type") === "benchmark";
      await route.fulfill(jsonRoute(isBenchmark ? [] : OPS_ARTIFACTS));
      return;
    }
    if (pathname.endsWith("/ops/audit-events")) {
      await route.fulfill(jsonRoute(AUDIT_EVENTS));
      return;
    }
    if (pathname.endsWith("/ops/snapshots")) {
      await route.fulfill(jsonRoute(SNAPSHOTS));
      return;
    }
    if (pathname.endsWith("/ops/releases")) {
      await route.fulfill(jsonRoute(releases));
      return;
    }
    if (pathname.endsWith("/ops/maintenance-windows")) {
      await route.fulfill(jsonRoute(WINDOWS));
      return;
    }
    if (pathname.endsWith("/ops/table-stats")) {
      await route.fulfill(jsonRoute(TABLE_STATS));
      return;
    }
    if (pathname.endsWith("/ops/pg-stat-statements")) {
      await route.fulfill(jsonRoute(PG_STATS));
      return;
    }
    // PerfValidationSummary의 consistency/source-match-sets 등 나머지는 빈 배열로 둔다.
    await route.fulfill(jsonRoute([]));
  });
}

test.describe("운영 콘솔 테이블 /admin/ops (T-271 VirtualTable)", () => {
  test("7개 ops 테이블이 데이터를 semantic <table>(caption)로 렌더한다", async ({ page }) => {
    await mockOpsApi(page);
    await page.goto("/admin/ops");

    // 각 테이블은 caption으로 접근 가능한 이름을 갖는다(semantic 전환 a11y 개선).
    const releasesTable = page.getByRole("table", { name: "서빙 릴리스 목록" });
    await expect(releasesTable).toBeVisible();
    await expect(releasesTable.getByRole("columnheader", { name: "release" })).toBeVisible();
    await expect(releasesTable.getByRole("cell", { name: "rel-1" })).toBeVisible();

    await expect(
      page.getByRole("table", { name: "데이터셋 스냅샷 목록" }).getByRole("cell", { name: "snap-1" })
    ).toBeVisible();

    const windowsTable = page.getByRole("table", { name: "유지보수 윈도우 목록" });
    await expect(windowsTable.getByRole("cell", { name: "full_load" })).toBeVisible();
    await expect(windowsTable.getByRole("cell", { name: "전국 재적재 운영 점검" })).toBeVisible();

    await expect(
      page
        .getByRole("table", { name: "테이블 통계 스냅샷 목록" })
        .getByRole("cell", { name: "public.mv_geocode_target" })
    ).toBeVisible();

    await expect(
      page.getByRole("table", { name: "pg_stat_statements 상위 쿼리 목록" }).getByText("SELECT * FROM")
    ).toBeVisible();

    await expect(
      page.getByRole("table", { name: "아티팩트 목록" }).getByRole("cell", { name: "consistency_report" })
    ).toBeVisible();

    await expect(
      page
        .getByRole("table", { name: "감사 이벤트 목록" })
        .getByRole("cell", { name: "maintenance_window.open" })
    ).toBeVisible();
  });

  test("빈 ops 테이블은 emptyHint 안내를 보여 준다", async ({ page }) => {
    await mockOpsApi(page, { releases: [] });
    await page.goto("/admin/ops");

    await expect(
      page.getByRole("table", { name: "서빙 릴리스 목록" }).getByText("서빙 릴리스가 없습니다.")
    ).toBeVisible();
  });

  test("한 ops 엔드포인트(503)가 실패해도 나머지 표는 채워진다 (allSettled 복원력)", async ({
    page
  }) => {
    await mockOpsApi(page);
    // pg-stat-statements만 503으로 덮어쓴다(가장 나중에 등록한 route가 우선).
    await page.route("**/api/proxy/v1/admin/ops/pg-stat-statements**", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "pg_stat_statements unavailable" })
      });
    });
    await page.goto("/admin/ops");

    // 한 엔드포인트 실패와 무관하게 나머지 표는 실데이터로 채워진다(Promise.all이었다면 전부 비었음).
    await expect(
      page.getByRole("table", { name: "서빙 릴리스 목록" }).getByRole("cell", { name: "rel-1" })
    ).toBeVisible();
    await expect(
      page.getByRole("table", { name: "데이터셋 스냅샷 목록" }).getByRole("cell", { name: "snap-1" })
    ).toBeVisible();

    // 실패한 pg-stat 표는 비어 있고(emptyHint), 실패 목록이 Last Response에 노출된다.
    await expect(
      page
        .getByRole("table", { name: "pg_stat_statements 상위 쿼리 목록" })
        .getByText("pg_stat_statements 스냅샷이 없습니다.")
    ).toBeVisible();
    await expect(page.getByText(/일부 ops 데이터 로드 실패/)).toBeVisible();
  });
});
