import { expect, test, type Page } from "@playwright/test";

// /admin/backups 복원 위저드 (T-249) e2e (T-256). 백엔드 admin API는 page.route로 목킹하므로
// DB/백엔드 없이 위저드의 4단계 흐름 — 모드 선택·manifest 미리보기·dry-run 검사·replace_current
// typed confirmation 게이팅·blocker 차단 — 을 production build에서 검증한다.
// backups.spec.ts(T-255)의 mock-fixture 하네스를 재사용한다.

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
    source_set_yyyymm: { juso: "202603", locsum: "202604" },
    source_set_mixed: true,
    source_inventory_ok: true,
    manifest: {
      backup: { profile: "serving-ready" },
      database: { postgres_version: "16.4", postgis_version: "3.5.2" },
      row_counts: { mv_geocode_target: 6_419_795 },
      active_serving: { serving_release_id: "rel-9" }
    }
  }
];

type DryRun = Record<string, unknown>;

const NEW_DB_OK: DryRun = {
  can_restore: true,
  mode: "new_database",
  target_database: "kor_travel_geo_restore",
  archive_sha256_ok: true,
  internal_checksums_ok: true,
  manifest_ok: true,
  backup_postgres_version: "16.4",
  backup_postgis_version: "3.5.2",
  target_postgres_version: "16.4",
  target_postgis_version: "3.5.2",
  blockers: [],
  warnings: ["대상 DB가 이미 존재하면 안 됩니다 — 미리 drop 하세요."]
};

const REPLACE_OK: DryRun = {
  ...NEW_DB_OK,
  mode: "replace_current",
  target_database: "kor_travel_geo"
};

const BLOCKED: DryRun = {
  can_restore: false,
  mode: "new_database",
  target_database: "kor_travel_geo_restore",
  archive_sha256_ok: false,
  internal_checksums_ok: true,
  manifest_ok: true,
  blockers: ["archive sha256 불일치 — bit rot 의심, 복원 불가"],
  warnings: []
};

const RESTORE_JOB = {
  job_id: "job-restore-1",
  kind: "db_restore",
  state: "queued",
  progress: 0,
  current_stage: "queued",
  started_at: "2026-06-16T00:00:00Z"
};

function jsonRoute(body: unknown) {
  return { contentType: "application/json", body: JSON.stringify(body) };
}

// dryRun 응답은 시나리오마다 다르므로 클로저로 주입한다.
async function mockRestoreApi(page: Page, dryRun: DryRun): Promise<void> {
  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill(jsonRoute({ vworldApiKey: "" }));
  });
  await page.route("**/api/proxy/v1/admin/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const method = route.request().method();

    if (pathname.endsWith("/events")) {
      await route.fulfill({ contentType: "text/event-stream", body: "" });
      return;
    }
    if (method === "POST" && pathname.endsWith("/admin/restores/dry-run")) {
      await route.fulfill(jsonRoute(dryRun));
      return;
    }
    if (method === "POST" && pathname.endsWith("/admin/restores")) {
      await route.fulfill(jsonRoute(RESTORE_JOB));
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
      await route.fulfill(jsonRoute([]));
      return;
    }
    if (pathname.endsWith("/admin/ops/artifacts")) {
      await route.fulfill(jsonRoute([]));
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
}

// 복원 탭으로 이동하고 위저드 Panel을 반환한다.
async function gotoRestoreWizard(page: Page) {
  await page.goto("/admin/backups");
  await page.getByRole("tab", { name: "복원" }).click();
  const wizard = page
    .locator("section.panel")
    .filter({ has: page.getByRole("heading", { name: "복원 위저드" }) });
  await expect(wizard).toBeVisible();
  return wizard;
}

test.describe("복원 위저드 /admin/backups (T-256)", () => {
  test("new_database: 모드·manifest 미리보기·dry-run·제출 happy path", async ({ page }) => {
    await mockRestoreApi(page, NEW_DB_OK);
    const wizard = await gotoRestoreWizard(page);

    // ① 백업·모드 선택 (mode는 new_database 기본값).
    await wizard.getByLabel("복원할 백업본 (artifact)").selectOption("art-available");
    await wizard.getByRole("button", { name: "다음" }).click();

    // ② manifest 미리보기 — profile/PG/PostGIS/row_counts (leaf 텍스트는 exact로 ancestor 충돌 회피).
    await expect(wizard.getByText("serving-ready", { exact: true })).toBeVisible();
    await expect(wizard.getByText("16.4", { exact: true })).toBeVisible();
    await expect(wizard.getByText("3.5.2", { exact: true })).toBeVisible();
    await expect(wizard.getByText("row_counts", { exact: true })).toBeVisible();
    await wizard.getByRole("button", { name: "dry-run 실행" }).click();

    // ③ dry-run 검사 — 복원 가능 verdict + 버전 비교 hint.
    await expect(wizard.getByText("복원 가능", { exact: true })).toBeVisible();
    await expect(wizard.getByText(/버전 —/)).toBeVisible();
    await wizard.getByRole("button", { name: "확인 단계로" }).click();

    // ④ 확인·실행 — new_database는 confirmation 불필요, can_restore=true면 제출 가능.
    const submitButton = wizard.getByRole("button", { name: "복원 시작" });
    await expect(submitButton).toBeEnabled();
    const restoreRequest = page.waitForRequest(
      (req) => req.url().endsWith("/admin/restores") && req.method() === "POST"
    );
    await submitButton.click();
    await restoreRequest;
    await expect(wizard.locator("p", { hasText: "복원 job이 제출됐습니다" })).toBeVisible();
  });

  test("replace_current: 정확한 typed confirmation 입력 전에는 제출이 차단된다", async ({
    page
  }) => {
    await mockRestoreApi(page, REPLACE_OK);
    const wizard = await gotoRestoreWizard(page);

    await wizard.getByLabel("복원할 백업본 (artifact)").selectOption("art-available");
    await wizard.getByLabel("복원 모드 (mode)").selectOption("replace_current");
    await wizard.getByLabel("복원 대상 DB 이름 (target_database)").fill("kor_travel_geo");
    await wizard.getByRole("button", { name: "다음" }).click();
    await wizard.getByRole("button", { name: "dry-run 실행" }).click();
    await expect(wizard.getByText("복원 가능", { exact: true })).toBeVisible();
    await wizard.getByRole("button", { name: "확인 단계로" }).click();

    // confirmation 미입력 → 제출 차단.
    const submitButton = wizard.getByRole("button", { name: "복원 시작" });
    await expect(wizard.getByText("RESTORE kor_travel_geo", { exact: true })).toBeVisible();
    await expect(submitButton).toBeDisabled();

    // 틀린 confirmation → 여전히 차단.
    const confirm = wizard.getByLabel("typed confirmation");
    await confirm.fill("RESTORE wrong");
    await expect(submitButton).toBeDisabled();

    // 정확한 confirmation → 제출 가능 + body에 confirmation 포함.
    await confirm.fill("RESTORE kor_travel_geo");
    await expect(submitButton).toBeEnabled();
    const restoreRequest = page.waitForRequest(
      (req) => req.url().endsWith("/admin/restores") && req.method() === "POST"
    );
    await submitButton.click();
    const body = (await restoreRequest).postDataJSON();
    expect(body.mode).toBe("replace_current");
    expect(body.confirmation).toBe("RESTORE kor_travel_geo");
  });

  test("dry-run이 복원 불가(blocker)면 복원 시작이 차단된다", async ({ page }) => {
    await mockRestoreApi(page, BLOCKED);
    const wizard = await gotoRestoreWizard(page);

    await wizard.getByLabel("복원할 백업본 (artifact)").selectOption("art-available");
    await wizard.getByRole("button", { name: "다음" }).click();
    await wizard.getByRole("button", { name: "dry-run 실행" }).click();

    // ③ 복원 불가 verdict + blocker 목록.
    await expect(wizard.getByText("복원 불가", { exact: true })).toBeVisible();
    await expect(
      wizard.getByText("archive sha256 불일치 — bit rot 의심, 복원 불가", { exact: true })
    ).toBeVisible();
    await wizard.getByRole("button", { name: "확인 단계로" }).click();

    // ④ blocker 경고(alert) + 제출 차단 (new_database라도 can_restore=false면 막힘).
    await expect(wizard.getByRole("alert")).toContainText("복원 불가로 판정");
    await expect(wizard.getByRole("button", { name: "복원 시작" })).toBeDisabled();
  });

  test("archive_path 직접 경로: manifest 안내 + dry-run·제출", async ({ page }) => {
    await mockRestoreApi(page, NEW_DB_OK);
    const wizard = await gotoRestoreWizard(page);

    // artifact 미선택 → archive_path 입력 경로.
    await wizard.getByLabel("백업본 직접 경로 (archive_path)").fill("/data/backups/manual.tar.zst");
    await wizard.getByRole("button", { name: "다음" }).click();

    // ② 직접 경로는 manifest 미리보기 대신 안내 문구.
    await expect(wizard.locator("p", { hasText: "manifest 미리보기는 등록된" })).toBeVisible();
    await wizard.getByRole("button", { name: "dry-run 실행" }).click();
    await expect(wizard.getByText("복원 가능", { exact: true })).toBeVisible();
    await wizard.getByRole("button", { name: "확인 단계로" }).click();

    const submitButton = wizard.getByRole("button", { name: "복원 시작" });
    await expect(submitButton).toBeEnabled();
    const restoreRequest = page.waitForRequest(
      (req) => req.url().endsWith("/admin/restores") && req.method() === "POST"
    );
    await submitButton.click();
    const body = (await restoreRequest).postDataJSON();
    expect(body.archive_path).toBe("/data/backups/manual.tar.zst");
    expect(body.artifact_id).toBeUndefined();
  });
});
