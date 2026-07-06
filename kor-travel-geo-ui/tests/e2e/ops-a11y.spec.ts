import { expect, test, type Page } from "@playwright/test";

// /admin/ops 접근성·회복성 e2e (T-227). 운영 콘솔(성능·검증 요약 read-only + ops 패널들)의
// 회복성(benchmark artifact 500 → role=alert로 graceful·다른 패널 생존, refresh 재적재)과
// 키보드(정합성 상세 링크 Enter 활성)를 백엔드 없이 page.route mock으로 고정한다.
// ops-perf-summary.spec.ts(T-222)는 콘텐츠/델타 표시를 검증하므로 여기서는 a11y/회복성만 추가한다.

const BENCHMARKS = [
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

type Opts = { artifactsStatus?: number };

function jsonRoute(body: unknown) {
  return { contentType: "application/json", body: JSON.stringify(body) };
}

async function mockOpsApi(page: Page, opts: Opts = {}): Promise<void> {
  const { artifactsStatus = 200 } = opts;
  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill(jsonRoute({ vworldApiKey: "" }));
  });
  await page.route("**/api/proxy/v1/admin/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;

    if (pathname.endsWith("/ops/artifacts")) {
      if (artifactsStatus !== 200) {
        await route.fulfill({ status: artifactsStatus, body: "artifact 조회 실패 (mock 500)" });
        return;
      }
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
    await route.fulfill(jsonRoute([]));
  });
}

test.describe("운영 콘솔 접근성·회복성 /admin/ops (T-227)", () => {
  test("회복성: benchmark artifact 500이어도 role=alert로 알리고 다른 패널이 생존한다", async ({
    page
  }) => {
    await mockOpsApi(page, { artifactsStatus: 500 });
    await page.goto("/admin/ops");

    // 성능·검증 요약 패널은 살아 있고 오류를 role=alert로 노출한다(앱이 죽지 않음).
    const perf = page.locator(".panel", { hasText: "성능·검증 요약" });
    await expect(perf).toBeVisible();
    await expect(perf.getByRole("alert")).toBeVisible();
    // 나머지 운영 패널(서빙 릴리스)도 여전히 렌더된다.
    await expect(page.getByRole("heading", { name: "서빙 릴리스", exact: true })).toBeVisible();
  });

  test("키보드: 정합성 상세 링크를 focus→Enter로 이동할 수 있다", async ({ page }) => {
    await mockOpsApi(page);
    await page.goto("/admin/ops");

    const perf = page.locator(".panel", { hasText: "성능·검증 요약" });
    const detail = perf.getByRole("link", { name: /상세/ });
    await detail.focus();
    await expect(detail).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/admin\/consistency/);
  });

  test("회복성: refresh 후 성능·검증 요약이 다시 적재된다", async ({ page }) => {
    await mockOpsApi(page);
    await page.goto("/admin/ops");

    const perf = page.locator(".panel", { hasText: "성능·검증 요약" });
    await expect(perf.getByText("load_matrix")).toBeVisible();

    await page.reload();
    await expect(perf.getByText("load_matrix")).toBeVisible();
    await expect(perf.getByText("활성: 활성 세트")).toBeVisible();
  });
});
