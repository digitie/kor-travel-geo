import { expect, test } from "@playwright/test";
import { liveAdminCredentials } from "./_live";

// Layer 2 — issue #513 regression, against a LIVE **production build** (next start / the
// deployed container). Gated behind LIVE_E2E like the rest of tests/e2e/live.
//
// WHY THIS MUST BE AN E2E TEST AND NOT A UNIT TEST
// -----------------------------------------------
// Revocation state lives in a module-scope Map. The bundler emits `lib/auth.ts` once per
// layer — route handlers, the SSR/RSC page layer, and Edge middleware each get their own
// module instance. A unit test imports the module exactly once, so revoke+verify always share
// one Map and the test passes even when production has three separate Maps and `/admin`
// happily renders for a logged-out cookie. That is precisely how #513 shipped, and how a first
// attempt at fixing it also looked green. Only a request against a real build catches it.
//
// The fix pins the state to `globalThis` (`lib/auth.ts`) so every same-process layer shares
// one Map, and re-validates in Node (`lib/session-guard.ts`) for pages + `/api/runtime-config`.

const PROTECTED_PAGES = [
  "/admin",
  "/admin/tables",
  // Server-renders KTG_DAGSTER_PUBLIC_URL, so a revoked session used to read config off it.
  "/admin/dagster",
  "/debug/geocode",
  // Matches the `[report_id]` dynamic route but is skipped by the middleware matcher's
  // `\.js$` negative lookahead — only the Node-side guard can gate it.
  "/admin/consistency/x.js"
];

test.describe("LIVE 세션 폐기 (#513)", () => {
  test("로그아웃 뒤 복사해 둔 쿠키로는 페이지도 런타임 설정도 얻을 수 없다", async ({
    playwright,
    baseURL
  }) => {
    test.skip(!process.env.LIVE_E2E, "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    const credentials = liveAdminCredentials();
    test.skip(
      !credentials,
      "Live admin auth test — set KTG_LIVE_E2E_ADMIN_PASSWORD without committing it"
    );
    const origin = baseURL ?? "http://127.0.0.1:12505";
    const api = await playwright.request.newContext({ baseURL: origin });

    // 1. Log in and capture the session cookie value (the "copied" credential).
    const login = await api.post("/api/auth/login", {
      headers: { origin },
      data: { username: credentials!.username, password: credentials!.password }
    });
    expect(login.status()).toBe(200);
    const cookies = await api.storageState();
    const session = cookies.cookies.find((c) => c.name === "ktg_ui_session");
    expect(session, "세션 쿠키가 발급되어야 한다").toBeTruthy();
    const cookieHeader = `ktg_ui_session=${session!.value}`;

    // 2. Sanity: the cookie works before logout.
    const before = await api.get("/admin", {
      headers: { cookie: cookieHeader },
      maxRedirects: 0
    });
    expect(before.status(), "로그아웃 전에는 접근된다").toBe(200);

    // 3. Log out — this revokes the session server-side.
    const logout = await api.post("/api/auth/logout", { headers: { origin, cookie: cookieHeader } });
    expect(logout.status()).toBe(200);

    // 4. Replay the copied cookie: every protected page must now refuse it.
    for (const path of PROTECTED_PAGES) {
      const response = await api.get(path, {
        headers: { cookie: cookieHeader },
        maxRedirects: 0
      });
      expect(
        response.status(),
        `${path} 는 폐기된 세션을 거부해야 한다 (리다이렉트)`
      ).toBeGreaterThanOrEqual(300);
      expect(response.status()).toBeLessThan(400);
      expect(response.headers()["location"] ?? "").toContain("/login");
    }

    // 5. …and the route that hands out the VWorld API key must 401 without leaking it.
    const runtimeConfig = await api.get("/api/runtime-config", {
      headers: { cookie: cookieHeader },
      maxRedirects: 0
    });
    expect(runtimeConfig.status()).toBe(401);
    expect(await runtimeConfig.text()).not.toContain("vworldApiKey");

    await api.dispose();
  });
});
