import { expect, test, type Locator, type Page } from "@playwright/test";

// /admin/backups Hot-swap 탭 (T-250) e2e (T-257). 백엔드 admin API는 page.route로 목킹하므로
// DB/백엔드 없이 hot-swap 상태기계(plan → maintenance window → typed confirmation 실행 →
// source 재검증 → rollback)와 blocker 차단을 production build에서 검증한다.
// backups.spec.ts(T-255)의 mock-fixture 하네스를 재사용한다.

type Plan = Record<string, unknown>;

const OK_PLAN: Plan = {
  current_database: "kor_travel_geo",
  restore_database: "kor_travel_geo_restore",
  previous_alias: "kor_travel_geo_prev_20260616",
  maintenance_database: "postgres",
  typed_confirmation: "SWAP kor_travel_geo",
  rollback_confirmation: "ROLLBACK kor_travel_geo",
  previous_alias_retention_days: 7,
  can_execute: true,
  blockers: [],
  steps: [
    "1. current(kor_travel_geo) → previous alias로 RENAME",
    "2. restore(kor_travel_geo_restore) → current로 RENAME",
    "3. serving smoke check 후 release lineage 기록"
  ],
  sql: ["ALTER DATABASE kor_travel_geo RENAME TO kor_travel_geo_prev_20260616"]
};

const BLOCKED_PLAN: Plan = {
  ...OK_PLAN,
  can_execute: false,
  blockers: ["active serving release가 없어 lineage를 기록할 수 없습니다 — 먼저 복원을 완료하세요."]
};

const WINDOW = {
  maintenance_window_id: "mw-1",
  kind: "restore",
  state: "active",
  reason: "restore hot-swap",
  created_at: "2026-06-16T00:00:00Z"
};

const SWAP_RESULT = {
  swapped: true,
  current_database: "kor_travel_geo",
  restore_database: "kor_travel_geo_restore",
  previous_alias: "kor_travel_geo_prev_20260616",
  rolled_back: false,
  smoke_ok: true,
  serving_release_id: "rel-10",
  previous_release_id: "rel-9"
};

const SOURCE_VERIFY = {
  entrypoint: "rename_hot_swap",
  run_quick_reconcile: true,
  mismatch_count: 0,
  reconstruct_unavailable: false,
  active_source_match_set_id: "ms-9"
};

const ROLLBACK_RESULT = {
  rolled_back: true,
  current_database: "kor_travel_geo",
  restore_database: "kor_travel_geo_restore",
  previous_alias: "kor_travel_geo_prev_20260616",
  smoke_ok: true,
  serving_release_id: "rel-9",
  previous_release_id: "rel-10"
};

function jsonRoute(body: unknown) {
  return { contentType: "application/json", body: JSON.stringify(body) };
}

// plan 응답은 시나리오마다 다르므로 클로저로 주입한다.
async function mockHotSwapApi(page: Page, plan: Plan): Promise<void> {
  await page.route("**/api/runtime-config", async (route) => {
    await route.fulfill(jsonRoute({ vworldApiKey: "" }));
  });
  await page.route("**/api/proxy/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const pathname = url.pathname;
    const method = route.request().method();

    if (pathname.endsWith("/events")) {
      await route.fulfill({ contentType: "text/event-stream", body: "" });
      return;
    }
    if (method === "POST" && pathname.endsWith("/restores/hot-swap-plan")) {
      await route.fulfill(jsonRoute(plan));
      return;
    }
    if (method === "POST" && pathname.endsWith("/ops/maintenance-windows")) {
      await route.fulfill(jsonRoute(WINDOW));
      return;
    }
    if (method === "POST" && pathname.endsWith("/restores/hot-swap-source-verify")) {
      await route.fulfill(jsonRoute(SOURCE_VERIFY));
      return;
    }
    if (method === "POST" && pathname.endsWith("/restores/hot-swap-rollback")) {
      await route.fulfill(jsonRoute(ROLLBACK_RESULT));
      return;
    }
    if (method === "POST" && pathname.endsWith("/restores/hot-swap")) {
      await route.fulfill(jsonRoute(SWAP_RESULT));
      return;
    }
    if (pathname.endsWith("/admin/backups/allowed-dirs")) {
      await route.fulfill(jsonRoute({ dirs: ["data/backups"], default_dir: "data/backups" }));
      return;
    }
    if (pathname.endsWith("/admin/backups")) {
      await route.fulfill(jsonRoute([]));
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

function panel(page: Page, name: RegExp): Locator {
  return page.locator("section.panel").filter({ has: page.getByRole("heading", { name }) });
}

async function gotoHotSwap(page: Page) {
  await page.goto("/admin/backups");
  await page.getByRole("tab", { name: "Hot-swap" }).click();
  await expect(panel(page, /Hot-swap plan/)).toBeVisible();
}

async function buildPlan(page: Page) {
  const planPanel = panel(page, /Hot-swap plan/);
  await planPanel.getByLabel("복원된 DB 이름 (restore_database)").fill("kor_travel_geo_restore");
  await planPanel.getByRole("button", { name: "plan 생성" }).click();
}

test.describe("Hot-swap 탭 /admin/backups (T-257)", () => {
  test("plan 생성: 실행 가능 plan 카드·단계를 렌더한다", async ({ page }) => {
    await mockHotSwapApi(page, OK_PLAN);
    await gotoHotSwap(page);
    await buildPlan(page);

    const planPanel = panel(page, /Hot-swap plan/);
    await expect(planPanel.getByText("가능", { exact: true })).toBeVisible();
    await expect(planPanel.getByText("kor_travel_geo_prev_20260616")).toBeVisible();
    await expect(
      planPanel.locator("li", { hasText: "serving smoke check 후 release lineage 기록" })
    ).toBeVisible();
  });

  test("blocker: can_execute=false면 blocker 목록 + window/실행이 차단된다", async ({ page }) => {
    await mockHotSwapApi(page, BLOCKED_PLAN);
    await gotoHotSwap(page);
    await buildPlan(page);

    const planPanel = panel(page, /Hot-swap plan/);
    await expect(planPanel.getByText("불가", { exact: true })).toBeVisible();
    await expect(
      planPanel.getByText("active serving release가 없어 lineage를 기록할 수 없습니다 — 먼저 복원을 완료하세요.", {
        exact: true
      })
    ).toBeVisible();

    // window 열기·실행 버튼이 차단된다.
    await expect(
      panel(page, /Maintenance window/).getByRole("button", { name: /maintenance window 열기/ })
    ).toBeDisabled();
    await expect(panel(page, /위험/).getByRole("button", { name: /hot-swap 실행/ })).toBeDisabled();
  });

  test("실행: window + 정확한 typed confirmation 순서로만 hot-swap이 실행된다", async ({ page }) => {
    await mockHotSwapApi(page, OK_PLAN);
    await gotoHotSwap(page);
    await buildPlan(page);

    const execPanel = panel(page, /위험/);
    const submit = execPanel.getByRole("button", { name: /hot-swap 실행/ });

    // window 미오픈 + confirmation 정확해도 실행 차단.
    await execPanel.getByLabel("typed confirmation").fill("SWAP kor_travel_geo");
    await expect(submit).toBeDisabled();

    // maintenance window 열기.
    const windowPanel = panel(page, /Maintenance window/);
    await windowPanel.getByRole("button", { name: /maintenance window 열기/ }).click();
    await expect(windowPanel.getByText("active", { exact: true })).toBeVisible();

    // 틀린 confirmation → 차단, 정확 → 실행 가능.
    await execPanel.getByLabel("typed confirmation").fill("SWAP wrong");
    await expect(submit).toBeDisabled();
    await execPanel.getByLabel("typed confirmation").fill("SWAP kor_travel_geo");
    await expect(submit).toBeEnabled();

    const swapRequest = page.waitForRequest(
      (req) => req.url().endsWith("/restores/hot-swap") && req.method() === "POST"
    );
    await submit.click();
    await swapRequest;
    await expect(execPanel.getByText("swap 완료", { exact: true })).toBeVisible();
    await expect(execPanel.locator("p", { hasText: "smoke: true" })).toBeVisible();
  });

  test("source 재검증 + rollback confirmation 게이팅", async ({ page }) => {
    await mockHotSwapApi(page, OK_PLAN);
    await gotoHotSwap(page);
    await buildPlan(page);

    const sidePanel = panel(page, /source 재검증/);

    // source 재검증.
    await sidePanel.getByRole("button", { name: "source 재검증" }).click();
    await expect(sidePanel.getByText("검증됨", { exact: true })).toBeVisible();
    await expect(sidePanel.locator("p", { hasText: "mismatch 0" })).toBeVisible();

    // rollback confirmation 게이팅.
    const rollbackButton = sidePanel.getByRole("button", { name: /rollback 실행/ });
    await sidePanel.getByLabel("rollback confirmation").fill("ROLLBACK wrong");
    await expect(rollbackButton).toBeDisabled();
    await sidePanel.getByLabel("rollback confirmation").fill("ROLLBACK kor_travel_geo");
    await expect(rollbackButton).toBeEnabled();

    const rollbackRequest = page.waitForRequest(
      (req) => req.url().endsWith("/restores/hot-swap-rollback") && req.method() === "POST"
    );
    await rollbackButton.click();
    await rollbackRequest;
  });
});
