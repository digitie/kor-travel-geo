import { expect, test, type APIResponse } from "@playwright/test";

import {
  KNOWN,
  directApiGet,
  directApiPost,
  isLiveE2EEnabled,
  liveAdminCredentials,
  liveApiBaseUrl,
  loginLiveAdmin,
  loginLiveAdminPage,
  proxyGet,
  proxyPost
} from "./_live";

type Row = Record<string, unknown>;

const LIVE_TIMEOUT = 15_000;

test.describe("LIVE admin auth and session security", () => {
  test.beforeEach(() => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
  });

  test("unauthenticated admin navigation redirects to login with next path", async ({ page }) => {
    await page.goto("/admin/settings");

    await expect(page.getByRole("heading", { name: "관리자 로그인" })).toBeVisible({
      timeout: LIVE_TIMEOUT
    });
    expect(page.url()).toContain("/login");
    expect(decodeURIComponent(page.url())).toContain("next=/admin/settings");
  });

  test("invalid and successful login attempts are stored and visible in Settings", async ({
    page
  }) => {
    const credentials = liveAdminCredentials();
    test.skip(credentials === null, "Set KTG_LIVE_E2E_ADMIN_PASSWORD for live admin auth tests");
    if (credentials === null) return;

    await page.goto("/login?next=/admin/settings");
    await page.getByLabel("아이디").fill(credentials.username);
    await page.getByLabel("비밀번호").fill(`wrong-${Date.now()}`);

    const [failedLogin] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes("/api/auth/login") && res.request().method() === "POST"
      ),
      page.getByRole("button", { name: "로그인" }).click()
    ]);
    expect(failedLogin.status()).toBe(401);
    await expect(page.getByText("아이디 또는 비밀번호가 올바르지 않습니다.")).toBeVisible();

    await page.getByLabel("비밀번호").fill(credentials.password);
    const [successfulLogin] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes("/api/auth/login") && res.request().method() === "POST"
      ),
      page.getByRole("button", { name: "로그인" }).click()
    ]);
    expect(successfulLogin.status()).toBe(200);
    await page.waitForURL("**/admin/settings", { timeout: LIVE_TIMEOUT });

    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({
      timeout: LIVE_TIMEOUT
    });
    await expect(page.getByRole("heading", { name: "로그인 기록" })).toBeVisible();
    await expect(page.getByText(/authenticated|invalid_credentials/).first()).toBeVisible({
      timeout: LIVE_TIMEOUT
    });
    await expect(page.getByText(/ip:[0-9a-f-]{1,10}|ip:-/).first()).toBeVisible({
      timeout: LIVE_TIMEOUT
    });
    await expect(page.getByText(/ua:[0-9a-f-]{1,10}|ua:-/).first()).toBeVisible({
      timeout: LIVE_TIMEOUT
    });
  });

  test("login cookie is httpOnly Strict and logout invalidates the admin session", async ({
    page
  }) => {
    await loginLiveAdminPage(page, "/admin/settings");
    const sessionCookie = (await page.context().cookies()).find(
      (cookie) => cookie.name === "ktg_ui_session"
    );
    expect(sessionCookie?.httpOnly).toBe(true);
    expect(sessionCookie?.sameSite).toBe("Strict");

    await page.goto("/admin/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({
      timeout: LIVE_TIMEOUT
    });

    const [logout] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes("/api/auth/logout") && res.request().method() === "POST"
      ),
      page.getByRole("button", { name: "로그아웃" }).click()
    ]);
    expect(logout.status()).toBe(200);
    const clearedCookie = (await page.context().cookies()).find(
      (cookie) => cookie.name === "ktg_ui_session"
    );
    expect(clearedCookie).toBeUndefined();

    await page.goto("/admin/settings");
    await expect(page.getByRole("heading", { name: "관리자 로그인" })).toBeVisible({
      timeout: LIVE_TIMEOUT
    });
  });

  test("auth audit API exposes login events with redacted client metadata", async ({ request }) => {
    await loginLiveAdmin(request, "/admin/settings");

    const response = await proxyGet(request, "v1/admin/ops/audit-events", {
      action: "admin_auth.login",
      limit: 20
    });
    expect(response.status()).toBe(200);
    const rows = (await response.json()) as Row[];
    expect(rows.length).toBeGreaterThan(0);
    const latest = rows[0];
    expect(latest.action).toBe("admin_auth.login");
    expect(["succeeded", "denied", "failed"]).toContain(latest.outcome);
    expect(typeof latest.payload_redacted).toBe("object");
    expect((latest.payload_redacted as Row).attempted_username).toBeTruthy();
    expect(String(latest.client_ip_hash ?? "").length).toBeGreaterThan(0);
    expect(String(latest.user_agent_hash ?? "").length).toBeGreaterThan(0);
  });
});

test.describe("LIVE public API key security", () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdmin(request);
  });

  test("trusted same-origin UI proxy can call v1 and v2 without a key or with a wrong key", async ({
    request
  }) => {
    const v1NoKey = await proxyGet(request, "v1/address/geocode", { address: KNOWN.address });
    expect(v1NoKey.status()).toBe(200);

    const v1WrongKey = await proxyGet(request, "v1/address/geocode", {
      address: KNOWN.address,
      key: "wrong-live-e2e-key"
    });
    expect(v1WrongKey.status()).toBe(200);

    const v2NoKey = await proxyPost(request, "v2/geocode", {
      query: KNOWN.address,
      limit: 1
    });
    expect(v2NoKey.status()).toBe(200);

    const v2WrongKey = await proxyPost(request, "v2/geocode?key=wrong-live-e2e-key", {
      query: KNOWN.address,
      limit: 1
    });
    expect(v2WrongKey.status()).toBe(200);
  });

  test("direct untrusted public API requires key for v1 and v2", async ({ request }) => {
    test.skip(liveApiBaseUrl() === null, "Set KTG_LIVE_E2E_API_BASE_URL for direct API checks");

    const missingV1 = await directApiGet(request, "v1/address/geocode", {
      address: KNOWN.address
    });
    expect(missingV1.status()).toBeGreaterThanOrEqual(400);
    const missingV1Body = (await missingV1.json()) as Row;
    expect((missingV1Body.response as Row).status).toBe("ERROR");

    const missingV2 = await directApiPost(request, "v2/geocode", {
      query: KNOWN.address,
      limit: 1
    });
    expect(missingV2.status()).toBe(400);
    const missingV2Body = (await missingV2.json()) as Row;
    expect(missingV2Body.status).toBe("ERROR");
    expect(String((missingV2Body.error as Row).hint ?? "")).toContain("key");

    const invalidV2 = await directApiPost(
      request,
      "v2/geocode",
      {
        query: KNOWN.address,
        limit: 1
      },
      { key: "wrong-live-e2e-key" }
    );
    expect(invalidV2.status()).toBe(401);
    const invalidV2Body = (await invalidV2.json()) as Row;
    expect((invalidV2Body.error as Row).code).toBe("E0401");
  });

  test("UI can generate a DB-backed key, use it directly, then revoke it", async ({
    browserName,
    page,
    request
  }) => {
    test.skip(
      process.env.KTG_LIVE_E2E_MUTATE_PUBLIC_KEYS !== "1",
      "Creates and revokes a DB public API key; set KTG_LIVE_E2E_MUTATE_PUBLIC_KEYS=1"
    );
    test.skip(liveApiBaseUrl() === null, "Set KTG_LIVE_E2E_API_BASE_URL for direct API checks");

    await loginLiveAdminPage(page, "/admin/settings");
    await page.goto("/admin/settings");
    const label = `live-e2e-${browserName}-${Date.now()}`;
    await page.getByLabel("키 이름").fill(label);

    const [createResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes("/api/proxy/v1/admin/public-api-keys") &&
          res.request().method() === "POST",
        { timeout: LIVE_TIMEOUT }
      ),
      page.getByRole("button", { name: "랜덤 키 생성" }).click()
    ]);
    expect(createResponse.status()).toBe(200);

    const generatedInput = page.getByLabel("생성된 키");
    await expect(generatedInput).toBeVisible({ timeout: LIVE_TIMEOUT });
    const generatedKey = await generatedInput.inputValue();
    expect(generatedKey.length).toBeGreaterThanOrEqual(24);
    await expect(page.getByText("이 키는 지금 한 번만 표시됩니다.")).toBeVisible();

    const directOk = await directApiPost(
      request,
      "v2/geocode",
      {
        query: KNOWN.address,
        limit: 1
      },
      { key: generatedKey }
    );
    expectStatusOk(directOk);

    const [revokeResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes("/api/proxy/v1/admin/public-api-keys/") &&
          res.request().method() === "DELETE",
        { timeout: LIVE_TIMEOUT }
      ),
      page.getByRole("button", { name: `${label} 키 폐기` }).click()
    ]);
    expect(revokeResponse.status()).toBe(200);
    await expect(page.getByText("공개 API 키를 폐기했습니다.")).toBeVisible({
      timeout: LIVE_TIMEOUT
    });

    const directRevoked = await directApiPost(
      request,
      "v2/geocode",
      {
        query: KNOWN.address,
        limit: 1
      },
      { key: generatedKey }
    );
    expect(directRevoked.status()).toBe(401);
  });
});

function expectStatusOk(response: APIResponse): void {
  expect(response.status()).toBe(200);
}
