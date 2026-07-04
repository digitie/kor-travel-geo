import { expect, test, type Page } from "@playwright/test";

// /admin/backups 접근성·회복성 e2e (T-258). 신규 백업/복원 표면(manifest 모달·탭·작업 카드)의
// 키보드(Esc·focus trap·focus 복귀)와 회복성(네트워크 오류·SSE 끊김·refresh 후 재적재)을
// 백엔드 없이 page.route mock fixture로 검증한다. 기존 표면(source-files/consistency/ops) a11y는
// T-227에서 다루므로 여기서는 중복을 피하고 backups 표면에 한정한다. backups.spec.ts(T-255) 하네스 재사용.

const ARTIFACTS = [
  {
    artifact_id: "art-available",
    artifact_type: "db_backup",
    state: "available",
    storage_kind: "local_file",
    display_name: "kor_travel_geo-20260616.tar.zst",
    size_bytes: 87_241_216,
    retention_class: "scheduled",
    expires_at: "2026-07-16T00:00:00Z",
    created_at: "2026-06-16T00:00:00Z",
    source_inventory_ok: true,
    manifest: {
      backup: { profile: "serving-ready" },
      active_serving: { serving_release_id: "rel-9" }
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
  log_tail: ["2026-06-16T00:00:30 [dump] pg_dump 12.0MiB/30.0MiB"]
};

type Opts = { backupsStatus?: number; eventsStatus?: number; jobs?: unknown[] };

function jsonRoute(body: unknown) {
  return { contentType: "application/json", body: JSON.stringify(body) };
}

async function mockApi(page: Page, opts: Opts = {}): Promise<void> {
  const { backupsStatus = 200, eventsStatus = 200, jobs = [] } = opts;
  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill(jsonRoute({ vworldApiKey: "" }));
  });
  await page.route("**/api/proxy/v1/admin/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;

    if (pathname.endsWith("/events")) {
      if (eventsStatus !== 200) {
        await route.fulfill({ status: eventsStatus, contentType: "text/event-stream", body: "" });
      } else {
        await route.fulfill({ contentType: "text/event-stream", body: "" });
      }
      return;
    }
    if (pathname.endsWith("/admin/backups/allowed-dirs")) {
      await route.fulfill(jsonRoute({ dirs: ["data/backups"], default_dir: "data/backups" }));
      return;
    }
    if (pathname.endsWith("/admin/backups")) {
      if (backupsStatus !== 200) {
        await route.fulfill({ status: backupsStatus, body: "백업 목록 조회 실패 (mock 500)" });
      } else {
        await route.fulfill(jsonRoute(ARTIFACTS));
      }
      return;
    }
    if (pathname.endsWith("/admin/jobs")) {
      await route.fulfill(jsonRoute(jobs));
      return;
    }
    if (pathname.endsWith("/admin/ops/artifacts")) {
      await route.fulfill(jsonRoute([]));
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
}

async function openManifestDialog(page: Page) {
  await page.goto("/admin/backups");
  await page.getByRole("tab", { name: "백업" }).click();
  await page.getByRole("button", { name: "manifest 보기" }).click();
  return page.getByRole("dialog", { name: "백업 manifest 재현성 뷰어" });
}

test.describe("백업/복원 접근성·회복성 /admin/backups (T-258)", () => {
  test("manifest 모달: 열면 포커스가 모달 안으로 이동, Esc로 닫히고 콘솔이 계속 조작된다", async ({
    page
  }) => {
    await mockApi(page);
    const dialog = await openManifestDialog(page);
    await expect(dialog).toBeVisible();

    // 열리면 포커스가 모달 안으로 이동한다 (radix Dialog auto-focus).
    await expect
      .poll(() => dialog.evaluate((el) => el.contains(document.activeElement)))
      .toBe(true);

    // Esc로 닫힌다(키보드 only).
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();

    // 닫은 뒤에도 콘솔이 정상 조작된다(focus가 막히거나 모달이 트랩되지 않음).
    await page.getByRole("tab", { name: "복원" }).click();
    await expect(page.getByRole("heading", { name: "복원 위저드" })).toBeVisible();
  });

  test("manifest 모달: Tab이 모달 안에 갇힌다 (focus trap)", async ({ page }) => {
    await mockApi(page);
    const dialog = await openManifestDialog(page);
    await expect(dialog).toBeVisible();

    // 열리면 포커스가 먼저 모달 안으로 이동한 뒤,
    await expect
      .poll(() => dialog.evaluate((el) => el.contains(document.activeElement)))
      .toBe(true);
    // Tab/Shift+Tab을 반복해도 포커스가 모달 안에 머문다 (radix FocusScope).
    for (const key of ["Tab", "Tab", "Tab", "Shift+Tab", "Shift+Tab"]) {
      await page.keyboard.press(key);
      expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
    }

    // 닫기 버튼을 키보드로 눌러 닫을 수 있다(키보드 only).
    await dialog.getByRole("button", { name: "닫기" }).focus();
    await page.keyboard.press("Enter");
    await expect(dialog).toBeHidden();
  });

  test("탭: 키보드(Enter)로 탭을 전환할 수 있다", async ({ page }) => {
    await mockApi(page);
    await page.goto("/admin/backups");

    await page.getByRole("tab", { name: "백업" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "DB Backup", exact: true })).toBeVisible();
  });

  test("회복성: 백업 목록 API 오류여도 콘솔이 죽지 않고 오류를 노출한다", async ({ page }) => {
    await mockApi(page, { backupsStatus: 500 });
    await page.goto("/admin/backups");

    // 5개 탭이 여전히 렌더되고(앱이 죽지 않음), 개요 '최근 결과'에 오류가 노출된다.
    for (const name of ["개요", "백업", "복원", "Hot-swap", "작업"]) {
      await expect(page.getByRole("tab", { name })).toBeVisible();
    }
    await expect(page.getByText(/mock 500/)).toBeVisible();
    // 오류 이후에도 탭 전환 등 상호작용이 가능하다.
    await page.getByRole("tab", { name: "백업" }).click();
    await expect(page.getByText("Backup Artifacts")).toBeVisible();
  });

  test("회복성: SSE(/events) 끊겨도 작업 카드가 폴링 스냅샷으로 렌더된다", async ({ page }) => {
    await mockApi(page, { eventsStatus: 500, jobs: [RUNNING_JOB] });
    await page.goto("/admin/backups");
    await page.getByRole("tab", { name: "작업" }).click();

    // SSE 실패(onerror→close) 후에도 폴링한 job 스냅샷으로 카드가 보인다.
    await expect(page.getByText(/db_backup · job-runn/)).toBeVisible();
    await expect(page.getByText(/dump · 42%/)).toBeVisible();
  });

  test("회복성: refresh 후 서버 상태(artifacts)가 다시 적재된다", async ({ page }) => {
    await mockApi(page);
    await page.goto("/admin/backups");
    await page.getByRole("tab", { name: "백업" }).click();
    await expect(page.getByText("kor_travel_geo-20260616.tar.zst")).toBeVisible();

    await page.reload();
    // refresh로 client 상태(활성 탭)는 초기화되지만 데이터는 API에서 재적재된다.
    await page.getByRole("tab", { name: "백업" }).click();
    await expect(page.getByText("kor_travel_geo-20260616.tar.zst")).toBeVisible();
  });
});
