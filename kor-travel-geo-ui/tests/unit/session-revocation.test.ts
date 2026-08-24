import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createSessionCookieValue,
  hashAdminPasswordForEnv,
  revokeSessionCookieValue,
  verifySessionCookieValueNow
} from "@/lib/auth";

/**
 * Issue #513 regression guard.
 *
 * `middleware.ts` runs on the Edge runtime and cannot see the revocation list that the Node
 * logout route writes, so a cookie copied before logout still satisfied it — `/admin` rendered
 * and `/api/runtime-config` handed back the VWorld API key. The fix re-validates in Node
 * (`lib/session-guard.ts`) for the page shells and for that key-returning route.
 *
 * These tests pin the Node-side contract the guard and the route depend on.
 */

const SESSION_SECRET = "0123456789abcdef0123456789abcdef";

async function makeEnv() {
  return {
    KTG_UI_ADMIN_USERNAME: "admin",
    KTG_UI_ADMIN_PASSWORD_HASH: await hashAdminPasswordForEnv("pw-for-tests"),
    KTG_UI_SESSION_SECRET: SESSION_SECRET
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("세션 폐기(revocation) — Node 재검증 (#513)", () => {
  it("로그아웃한 쿠키는 Node 재검증에서 거부된다", async () => {
    const env = await makeEnv();
    const source = new Headers({ "user-agent": "revocation-test" });
    const cookie = await createSessionCookieValue(source, env);

    // Before logout the very same cookie is accepted…
    await expect(verifySessionCookieValueNow(cookie, env, source)).resolves.toBe(true);

    await revokeSessionCookieValue(cookie, env);

    // …and after logout it must be rejected even though the signature/expiry are still valid.
    // This is exactly the copied-cookie replay from #513.
    await expect(verifySessionCookieValueNow(cookie, env, source)).resolves.toBe(false);
  });

  it("한 세션을 폐기해도 다른 세션은 살아있다", async () => {
    const env = await makeEnv();
    const source = new Headers({ "user-agent": "revocation-test" });
    const first = await createSessionCookieValue(source, env);
    const second = await createSessionCookieValue(source, env);

    await revokeSessionCookieValue(first, env);

    await expect(verifySessionCookieValueNow(first, env, source)).resolves.toBe(false);
    await expect(verifySessionCookieValueNow(second, env, source)).resolves.toBe(true);
  });
});

describe("/api/runtime-config 는 세션을 직접 검증한다 (#513)", () => {
  it("세션이 무효하면 401을 주고 VWorld 키를 노출하지 않는다", async () => {
    vi.doMock("@/lib/session-guard", () => ({ sessionIsValidInNode: async () => false }));
    vi.doMock("@/lib/runtime-config", () => ({
      resolveVWorldApiKey: () => "SECRET-VWORLD-KEY",
      resolveDagsterPublicUrl: () => "http://dagster.invalid"
    }));
    const { GET } = await import("@/app/api/runtime-config/route");

    const response = await GET();
    expect(response.status).toBe(401);
    const body = await response.text();
    expect(body).not.toContain("SECRET-VWORLD-KEY");
    vi.doUnmock("@/lib/session-guard");
    vi.doUnmock("@/lib/runtime-config");
    vi.resetModules();
  });

  it("세션이 유효하면 런타임 설정을 반환한다", async () => {
    vi.doMock("@/lib/session-guard", () => ({ sessionIsValidInNode: async () => true }));
    vi.doMock("@/lib/runtime-config", () => ({
      resolveVWorldApiKey: () => "SECRET-VWORLD-KEY",
      resolveDagsterPublicUrl: () => "http://dagster.invalid"
    }));
    const { GET } = await import("@/app/api/runtime-config/route");

    const response = await GET();
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      vworldApiKey: "SECRET-VWORLD-KEY"
    });
    vi.doUnmock("@/lib/session-guard");
    vi.doUnmock("@/lib/runtime-config");
    vi.resetModules();
  });
});
