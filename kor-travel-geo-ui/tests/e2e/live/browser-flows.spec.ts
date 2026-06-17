import { expect, test } from "@playwright/test";
import { KNOWN } from "./_live";

// Layer 2 — real browser driving the debug pages against the LIVE backend.
//
// Unlike tests/e2e/debug-v2.spec.ts (which mocks every `page.route`), these specs let the
// real `/api/proxy/v2/*` and `/api/proxy/v1/*` calls flow through the same-origin proxy to the
// live FastAPI + PostgreSQL/PostGIS stack. They are GATED behind LIVE_E2E so the default
// (no backend) run skips them. See docs/live-e2e.md.
//
// baseURL is the live UI (http://127.0.0.1:12505); the API is reached via the same-origin proxy.

const LIVE_TIMEOUT = 15_000;

test.describe("LIVE debug browser flows", () => {
  test.beforeEach(() => {
    test.skip(!process.env.LIVE_E2E, "Live full-stack test — run with LIVE_E2E=1 and the stack up (DB+API+UI)");
  });

  test("geocode 디버그 화면이 KNOWN 주소를 실제 백엔드로 지오코딩한다", async ({ page }) => {
    await page.goto("/debug/geocode");
    await expect(page.getByRole("heading", { name: "Geocode" })).toBeVisible();

    // Fill the address/query input (#address) with the ground-truth anchor address.
    await page.locator("#address").fill(KNOWN.address);

    // Click 실행 (run) and wait for the LIVE POST to /api/proxy/v2/geocode to come back 2xx.
    const [response] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes("/api/proxy/v2/geocode") &&
          res.request().method() === "POST" &&
          res.status() >= 200 &&
          res.status() < 300,
        { timeout: LIVE_TIMEOUT }
      ),
      page.getByRole("button", { name: "실행" }).click()
    ]);
    expect(response.ok()).toBe(true);

    // The live geocode result is rendered in the 응답 JsonBlock; it must contain the road name.
    await expect(page.getByText(KNOWN.roadName).first()).toBeVisible({ timeout: LIVE_TIMEOUT });
  });

  test("reverse 디버그 화면이 KNOWN 좌표를 실제 백엔드로 역지오코딩한다", async ({ page }) => {
    await page.goto("/debug/reverse");
    await expect(page.getByRole("heading", { name: "Reverse" })).toBeVisible();

    // The component labels the inputs lon/lat but the ids are #x (lon) and #y (lat).
    await page.locator("#x").fill(String(KNOWN.lon));
    await page.locator("#y").fill(String(KNOWN.lat));

    // Click 조회 (run) and wait for the LIVE POST to /api/proxy/v2/reverse to come back 2xx.
    const [response] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes("/api/proxy/v2/reverse") &&
          res.request().method() === "POST" &&
          res.status() >= 200 &&
          res.status() < 300,
        { timeout: LIVE_TIMEOUT }
      ),
      page.getByRole("button", { name: "조회" }).click()
    ]);
    expect(response.ok()).toBe(true);

    // Around 서울시청 the live response should surface 중구 and/or 세종대로.
    await expect(
      page.getByText(/중구|세종대로/).first()
    ).toBeVisible({ timeout: LIVE_TIMEOUT });
  });

  test("normalize 디버그 화면이 KNOWN 주소를 실제 백엔드로 정규화한다", async ({ page }) => {
    await page.goto("/debug/normalize");
    await expect(page.getByRole("heading", { name: "Normalize" })).toBeVisible();

    // The normalize input id is #normalize-address.
    await page.locator("#normalize-address").fill(KNOWN.address);

    // postJson("/admin/normalize", …) resolves to /api/proxy/v1/admin/normalize (backendPath
    // prepends /v1 for non-v1/v2 paths). Click 토큰화 (run) and await that POST 2xx.
    const [response] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes("/api/proxy/v1/admin/normalize") &&
          res.request().method() === "POST" &&
          res.status() >= 200 &&
          res.status() < 300,
        { timeout: LIVE_TIMEOUT }
      ),
      page.getByRole("button", { name: "토큰화" }).click()
    ]);
    expect(response.ok()).toBe(true);

    // The normalized structure renders in the 정규화 결과 JsonBlock; it must echo the sido/sigungu.
    await expect(
      page.getByText(/서울특별시|중구/).first()
    ).toBeVisible({ timeout: LIVE_TIMEOUT });
  });
});
