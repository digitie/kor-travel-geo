import { expect, test } from "@playwright/test";

import {
  directApiPost,
  isLiveE2EEnabled,
  liveApiBaseUrl,
  loginLiveAdmin,
  loginLiveAdminPage,
  proxyGet,
  proxyPost
} from "./_live";

// LIVE tests for T-291b/c/d (ADR-067) — the external dataset-version change-detection API and
// its admin-surface projection. Read-only except the last test (public API key create+revoke),
// which is gated behind KTG_LIVE_E2E_MUTATE_PUBLIC_KEYS=1 matching the existing convention
// (auth-public-api-keys-live.spec.ts).

const LIVE_TIMEOUT = 15_000;

type DatasetVersionEntry = {
  version_token: string;
  activated_at: string;
  change_type: "full" | "delta";
  reference_months?: Record<string, string>;
  reference_months_mixed?: boolean;
};
type DatasetVersionResponse = {
  status: string;
  available: boolean;
  changed?: boolean;
  known_version_found?: boolean;
  current?: DatasetVersionEntry;
};
type DatasetHistoryResponse = {
  status: string;
  since_found?: boolean;
  entries: DatasetVersionEntry[];
  next_cursor?: string;
};

test.describe("LIVE dataset-version API", () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdmin(request);
  });

  test("admin ops/releases carries the same version_token the trusted-proxy preview returns", async ({
    request
  }) => {
    const releases = await proxyGet(request, "v1/admin/ops/releases", {
      state: "active",
      limit: 1
    });
    expect(releases.status()).toBe(200);
    const rows = (await releases.json()) as Array<{ version_token?: string }>;
    test.skip(rows.length === 0, "No live active serving release");

    const preview = await proxyPost(request, "v2/dataset/version", {});
    expect(preview.status()).toBe(200);
    const body = (await preview.json()) as DatasetVersionResponse;
    expect(body.available).toBe(true);
    expect(body.current?.version_token).toBe(rows[0].version_token);
  });

  test("known_version round trip reports changed:false for the current token", async ({
    request
  }) => {
    const current = await proxyPost(request, "v2/dataset/version", {});
    expect(current.status()).toBe(200);
    const currentBody = (await current.json()) as DatasetVersionResponse;
    test.skip(!currentBody.available, "No active serving release");
    const token = currentBody.current!.version_token;

    const res = await proxyPost(request, "v2/dataset/version", { known_version: token });
    expect(res.status()).toBe(200);
    const body = (await res.json()) as DatasetVersionResponse;
    expect(body.changed).toBe(false);
    expect(body.known_version_found).toBe(true);
  });

  test("known_version format is validated before any lookup", async ({ request }) => {
    const res = await proxyPost(request, "v2/dataset/version", { known_version: "not-a-token" });
    expect(res.status()).toBe(400);
    const body = (await res.json()) as { status: string; error?: { code?: string } };
    expect(body.status).toBe("ERROR");
  });

  test("history returns entries and a since_version anchor excludes itself", async ({
    request
  }) => {
    const history = await proxyPost(request, "v2/dataset/history", { limit: 5 });
    expect(history.status()).toBe(200);
    const body = (await history.json()) as DatasetHistoryResponse;
    expect(Array.isArray(body.entries)).toBe(true);
    test.skip(body.entries.length < 2, "Need at least 2 history entries for a since_version check");

    const anchor = body.entries[body.entries.length - 1].version_token;
    const since = await proxyPost(request, "v2/dataset/history", {
      since_version: anchor,
      limit: 5
    });
    expect(since.status()).toBe(200);
    const sinceBody = (await since.json()) as DatasetHistoryResponse;
    expect(sinceBody.since_found).toBe(true);
    expect(sinceBody.entries.some((entry) => entry.version_token === anchor)).toBe(false);
  });

  // Cache-Control 확인은 실 공개 API 직접 호출로만 검증한다 — 신뢰 admin 프록시(app/api/proxy/
  // [...path]/route.ts)는 upstream 응답 헤더를 content-type만 골라 전달하고 나머지는 버린다
  // (모든 admin 엔드포인트에 공통인 기존 동작, T-291d로 인한 변화 아님 — 자세한 배경/영향은
  // T-294). proxyPost로는 이 검증이 구조적으로 불가능하므로 known_version 라운드트립 테스트에
  // 흡수하지 않고, 아래 mutate opt-in 테스트에서 실 공개 키로 직접 호출해 확인한다.

  test("UI can generate a public API key and call /v2/dataset/version directly, matching the admin preview", async ({
    browserName,
    page,
    request
  }) => {
    test.skip(
      process.env.KTG_LIVE_E2E_MUTATE_PUBLIC_KEYS !== "1",
      "Creates and revokes a DB public API key; set KTG_LIVE_E2E_MUTATE_PUBLIC_KEYS=1"
    );
    test.skip(liveApiBaseUrl() === null, "Set KTG_LIVE_E2E_API_BASE_URL for direct API checks");

    const preview = await proxyPost(request, "v2/dataset/version", {});
    expect(preview.status()).toBe(200);
    const previewBody = (await preview.json()) as DatasetVersionResponse;
    test.skip(!previewBody.available, "No active serving release");

    await loginLiveAdminPage(page, "/admin/settings");
    await page.goto("/admin/settings");
    const label = `live-e2e-dataset-version-${browserName}-${Date.now()}`;
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

    try {
      const direct = await directApiPost(request, "v2/dataset/version", {}, { key: generatedKey });
      expect(direct.status()).toBe(200);
      // 실 공개 API 직접 호출에서만 검증 가능 — 신뢰 admin 프록시는 upstream Cache-Control을
      // 전달하지 않는다(T-294).
      expect(direct.headers()["cache-control"]).toBe("no-store");
      const directBody = (await direct.json()) as DatasetVersionResponse;
      // The direct, real-public-API-key call must return the SAME token the trusted-proxy
      // preview reported — the preview's "limitation" (ADR-067 D6) is that it bypasses auth,
      // not that it renders a different body. This test is what closes that gap: it proves
      // the auth PATH itself also reaches the identical response.
      expect(directBody.current?.version_token).toBe(previewBody.current?.version_token);
    } finally {
      await page.getByRole("button", { name: `${label} 키 폐기` }).click();
      await Promise.all([
        page.waitForResponse(
          (res) =>
            res.url().includes("/api/proxy/v1/admin/public-api-keys/") &&
            res.request().method() === "DELETE",
          { timeout: LIVE_TIMEOUT }
        ),
        page.getByRole("button", { name: "폐기", exact: true }).click()
      ]);
    }
  });
});
