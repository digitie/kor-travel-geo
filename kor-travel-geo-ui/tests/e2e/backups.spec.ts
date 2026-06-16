import { expect, test, type Page } from "@playwright/test";

// /admin/backups (T-248~T-254) e2e. 백엔드 admin API는 page.route로 목킹하므로 DB/백엔드 없이
// 백업/복원 콘솔의 핵심 흐름(생성·진행률·다운로드·삭제·취소·만료/검증)을 검증한다 (T-255).

const ARTIFACTS = [
  {
    artifact_id: "art-available",
    artifact_type: "db_backup",
    state: "available",
    storage_kind: "local_file",
    display_name: "kor_travel_geo-20260616.tar.zst",
    size_bytes: 87_241_216,
    sha256: "abc123def456",
    retention_class: "scheduled",
    expires_at: "2026-07-16T00:00:00Z",
    created_at: "2026-06-16T00:00:00Z",
    download_url: "/v1/admin/backups/art-available/download?token=" + "t".repeat(64),
    source_set_yyyymm: { juso: "202603", locsum: "202604" },
    source_set_mixed: true,
    source_inventory_ok: false,
    manifest: {
      backup: { profile: "serving-ready" },
      database: { postgres_version: "16.4", postgis_version: "3.5.2" },
      row_counts: { mv_geocode_target: 6_419_795 },
      source_inventory_verification: { ok: false, missing: 2 },
      active_serving: {
        serving_release_id: "rel-9",
        dataset_snapshot_id: "snap-9",
        source_match_set_id: "ms-9"
      }
    }
  }
];

const RUNNING_JOB = {
  job_id: "job-running-1234",
  kind: "db_backup",
  state: "running",
  progress: 0.42,
  current_stage: "dump",
  started_at: "2026-06-16T00:00:00Z",
  log_tail: ["2026-06-16T00:00:30 [dump] pg_dump 디렉터리 12.0MiB/30.0MiB"]
};

function jsonRoute(body: unknown) {
  return { contentType: "application/json", body: JSON.stringify(body) };
}

async function mockBackupsApi(page: Page): Promise<void> {
  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill(jsonRoute({ vworldApiKey: "" }));
  });
  await page.route("**/api/proxy/v1/admin/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const method = route.request().method();

    // SSE job-events: end the stream immediately so the hook closes (no reconnect).
    if (pathname.endsWith("/events")) {
      await route.fulfill({ contentType: "text/event-stream", body: "" });
      return;
    }
    if (method === "POST" && pathname.endsWith("/admin/backups")) {
      await route.fulfill(jsonRoute({ ...RUNNING_JOB, job_id: "job-new", progress: 0.01 }));
      return;
    }
    if (method === "POST" && /\/admin\/backups\/[^/]+\/delete$/.test(pathname)) {
      await route.fulfill(jsonRoute({ ...ARTIFACTS[0], state: "deleted" }));
      return;
    }
    if (method === "POST" && /\/admin\/jobs\/[^/]+\/cancel$/.test(pathname)) {
      await route.fulfill(jsonRoute({ ...RUNNING_JOB, state: "cancelled" }));
      return;
    }
    if (pathname.endsWith("/admin/backups/allowed-dirs")) {
      await route.fulfill(jsonRoute({ dirs: ["data/backups"], default_dir: "data/backups" }));
      return;
    }
    if (pathname.endsWith("/admin/backups")) {
      await route.fulfill(jsonRoute(ARTIFACTS));
      return;
    }
    if (pathname.endsWith("/admin/jobs")) {
      await route.fulfill(jsonRoute([RUNNING_JOB]));
      return;
    }
    if (pathname.endsWith("/admin/ops/artifacts")) {
      await route.fulfill(jsonRoute([]));
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
}

test.describe("백업/복원 콘솔 /admin/backups", () => {

  test("5개 탭과 개요의 다음-액션 가이드를 렌더한다", async ({ page }) => {
    await mockBackupsApi(page);
    await page.goto("/admin/backups");

    await expect(page.getByRole("tablist", { name: "백업/복원 관리 탭" })).toBeVisible();
    for (const name of ["개요", "백업", "복원", "Hot-swap", "작업"]) {
      await expect(page.getByRole("tab", { name })).toBeVisible();
    }
    await expect(page.getByText("백업/복원 다음 액션")).toBeVisible();
  });

  test("백업 탭: 생성 폼 + 만료/검증 컬럼이 있는 artifact 목록을 보여 준다", async ({ page }) => {
    await mockBackupsApi(page);
    await page.goto("/admin/backups");
    await page.getByRole("tab", { name: "백업" }).click();

    await expect(page.getByRole("heading", { name: "DB Backup", exact: true })).toBeVisible();
    await expect(page.getByText("Backup Artifacts")).toBeVisible();
    // VirtualTable 행이 실제 브라우저 레이아웃에서 렌더된다(만료/검증 컬럼 포함).
    await expect(page.getByText("kor_travel_geo-20260616.tar.zst")).toBeVisible();
    await expect(page.getByText("scheduled")).toBeVisible();
    // source 인벤토리 검증 실패 → '불일치' 배지.
    await expect(page.getByText("불일치").first()).toBeVisible();
  });

  test("백업 생성: 폼 제출이 db_backup 생성 요청을 보낸다", async ({ page }) => {
    await mockBackupsApi(page);
    await page.goto("/admin/backups");
    await page.getByRole("tab", { name: "백업" }).click();

    const createRequest = page.waitForRequest(
      (req) => req.url().includes("/admin/backups") && req.method() === "POST"
    );
    await page.getByRole("button", { name: "백업 시작" }).click();
    await createRequest;
  });

  test("artifact 목록 검색으로 행을 필터링한다 (VirtualTable)", async ({ page }) => {
    await mockBackupsApi(page);
    await page.goto("/admin/backups");
    await page.getByRole("tab", { name: "백업" }).click();
    await expect(page.getByText("kor_travel_geo-20260616.tar.zst")).toBeVisible();

    await page.getByLabel("목록 검색").fill("nomatch-xyz");
    await expect(page.getByText("kor_travel_geo-20260616.tar.zst")).toHaveCount(0);
    await page.getByLabel("목록 검색").fill("20260616");
    await expect(page.getByText("kor_travel_geo-20260616.tar.zst")).toBeVisible();
  });

  test("manifest 재현성 뷰어를 열어 source_set·active serving lineage를 보여 준다", async ({
    page
  }) => {
    await mockBackupsApi(page);
    await page.goto("/admin/backups");
    await page.getByRole("tab", { name: "백업" }).click();
    await page.getByRole("button", { name: "manifest 보기" }).click();

    const dialog = page.getByRole("dialog", { name: "백업 manifest 재현성 뷰어" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("source_set 기준월")).toBeVisible();
    await expect(dialog.getByText("release · rel-9")).toBeVisible();
    await dialog.getByRole("button", { name: "닫기" }).click();
    await expect(dialog).toBeHidden();
  });

  test("작업 탭: 진행 중 job의 실시간 진행률 카드와 취소를 보여 준다", async ({ page }) => {
    await mockBackupsApi(page);
    await page.goto("/admin/backups");
    await page.getByRole("tab", { name: "작업" }).click();

    await expect(page.getByText("Backup / Restore Jobs")).toBeVisible();
    // JobProgress 카드(폴링 fallback row 기준): kind + job id prefix + 단계/퍼센트.
    await expect(page.getByText(/db_backup · job-runn/)).toBeVisible();
    await expect(page.getByText(/dump · 42%/)).toBeVisible();

    const cancelRequest = page.waitForRequest(
      (req) => req.url().includes("/cancel") && req.method() === "POST"
    );
    await page.getByTitle("취소").click();
    await cancelRequest;
  });

  test("작업 탭: 작업이 없으면 빈 상태 안내를 보여 준다 (T-226)", async ({ page }) => {
    await mockBackupsApi(page);
    // jobs를 빈 배열로 덮어쓴다(마지막 등록 route 우선).
    await page.route("**/api/proxy/v1/admin/jobs**", async (route) => {
      await route.fulfill({ contentType: "application/json", body: "[]" });
    });
    await page.goto("/admin/backups");
    await page.getByRole("tab", { name: "작업" }).click();

    await expect(page.getByText("Backup / Restore Jobs")).toBeVisible();
    await expect(page.getByText("진행 중이거나 완료된 백업/복원 작업이 없습니다.")).toBeVisible();
  });
});
