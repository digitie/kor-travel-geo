import { expect, test, type Page } from "@playwright/test";

// T-222 e2e: /admin/ops 성능·검증 요약(read-only). benchmark(T-265 artifact_type=benchmark)
// latest-vs-baseline 비교, C1~C17 정합성 최신 상태, source match set 상태를 백엔드 없이
// page.route mock으로 고정한다.

const BENCHMARKS = [
  {
    artifact_id: "bench-old-1234",
    artifact_type: "benchmark",
    state: "available",
    storage_kind: "local_file",
    storage_uri: "F:/dev/geodata/t141/r0/report.json",
    created_at: "2026-06-15T00:00:00Z",
    manifest: {
      kind: "load_matrix",
      profile: "actual_mix/steady",
      workload: "actual_mix",
      phase: "steady",
      captured_at: "2026-06-15T00:00:00Z",
      metrics: { p95_ms: 10.0, p99_ms: 20.0, error_rate: 0, qps: 500 }
    }
  },
  {
    artifact_id: "bench-new-5678",
    artifact_type: "benchmark",
    state: "available",
    storage_kind: "local_file",
    storage_uri: "F:/dev/geodata/t141/r1/report.json",
    created_at: "2026-06-16T00:00:00Z",
    manifest: {
      kind: "load_matrix",
      profile: "actual_mix/steady",
      workload: "actual_mix",
      phase: "steady",
      captured_at: "2026-06-16T00:00:00Z",
      metrics: { p95_ms: 12.0, p99_ms: 18.0, error_rate: 0, qps: 540 }
    }
  }
];

const CONSISTENCY = [
  {
    report_id: "rep_1",
    scope: "full",
    severity_max: "WARN",
    generated_by: "cli",
    started_at: "2026-06-16T00:00:00Z",
    finished_at: "2026-06-16T00:01:00Z",
    source_set: {}
  }
];

const MATCH_SETS = [
  {
    source_match_set_id: "ms_active",
    name: "활성 세트",
    profile: "serving_recommended",
    state: "active",
    integrity_alert: false,
    mixed_yyyymm: false,
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-12T00:00:00Z"
  }
];

function jsonRoute(body: unknown) {
  return { contentType: "application/json", body: JSON.stringify(body) };
}

async function mockOpsApi(page: Page): Promise<void> {
  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill(jsonRoute({ vworldApiKey: "" }));
  });
  await page.route("**/api/proxy/v1/admin/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;

    if (pathname.endsWith("/ops/artifacts")) {
      const isBenchmark = url.searchParams.get("artifact_type") === "benchmark";
      await route.fulfill(jsonRoute(isBenchmark ? BENCHMARKS : []));
      return;
    }
    if (pathname.endsWith("/consistency")) {
      await route.fulfill(jsonRoute(CONSISTENCY));
      return;
    }
    if (pathname.includes("/source-match-sets")) {
      await route.fulfill(jsonRoute(MATCH_SETS));
      return;
    }
    // OpsPanel의 나머지 fetch는 모두 빈 배열로.
    await route.fulfill(jsonRoute([]));
  });
}

test.describe("성능·검증 요약 /admin/ops (T-222)", () => {
  test("benchmark latest-vs-baseline·C1~C17·매칭 세트 상태를 read-only로 노출한다", async ({
    page
  }) => {
    await mockOpsApi(page);
    const rscRequests: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("_rsc=")) {
        rscRequests.push(request.url());
      }
    });
    await page.goto("/admin/ops");

    const panel = page.locator(".panel", { hasText: "성능·검증 요약" });
    await expect(panel).toBeVisible();

    // 성능 benchmark: load_matrix 그룹의 최신 p95=12.0 + baseline 대비 delta(▲2.0 회귀).
    await expect(panel.getByText("load_matrix")).toBeVisible();
    await expect(panel.getByText("12.0")).toBeVisible();
    await expect(panel.locator(".perf-delta.warn", { hasText: "2.0" }).first()).toBeVisible();
    // p99는 개선(18.0, ▼2.0) → ok delta.
    await expect(panel.locator(".perf-delta.ok").first()).toBeVisible();

    // C1~C17: 최신 정합성 severity 배지 + 상세 링크.
    await expect(panel.getByText("WARN", { exact: true })).toBeVisible();
    await expect(panel.getByRole("link", { name: /상세/ })).toHaveAttribute(
      "href",
      "/admin/consistency"
    );
    // 매칭 세트: 활성 세트 노출.
    await expect(panel.getByText("활성: 활성 세트")).toBeVisible();

    await panel.getByRole("link", { name: /상세/ }).click();
    await expect(page.getByRole("heading", { name: "정합성 검증", exact: true })).toBeVisible();
    expect(rscRequests).toEqual([]);
  });

  test("benchmark artifact가 없으면 등록 안내를 보여 준다", async ({ page }) => {
    await page.route("**/api/runtime-config", async (route) => {
      await route.fulfill(jsonRoute({ vworldApiKey: "" }));
    });
    await page.route("**/api/proxy/v1/admin/**", async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname.endsWith("/consistency")) {
        await route.fulfill(jsonRoute(CONSISTENCY));
        return;
      }
      if (pathname.includes("/source-match-sets")) {
        await route.fulfill(jsonRoute(MATCH_SETS));
        return;
      }
      await route.fulfill(jsonRoute([])); // benchmark 포함 전부 빈 배열
    });
    await page.goto("/admin/ops");

    const panel = page.locator(".panel", { hasText: "성능·검증 요약" });
    await expect(panel.getByText("등록된 benchmark artifact가 없습니다", { exact: false })).toBeVisible();
  });
});
