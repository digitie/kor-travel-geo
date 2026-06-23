import { describe, expect, it } from "vitest";

import {
  SESSION_TTL_SECONDS,
  checkLoginRateLimit,
  clearLoginFailures,
  createSessionCookieValue,
  hashAdminPasswordForEnv,
  recordLoginFailure,
  revokeSessionCookieValue,
  sanitizeLocalPath,
  verifyAdminLogin,
  verifySessionCookieValue
} from "@/lib/auth";

const SESSION_SECRET = "0123456789abcdef0123456789abcdef";
const TEST_PASSWORD = "unit-test-admin-password";

describe("admin auth", () => {
  it("PBKDF2 env hash로 관리자 비밀번호를 검증한다", async () => {
    const env = await makeEnv(TEST_PASSWORD);

    await expect(
      verifyAdminLogin({ username: "admin", password: TEST_PASSWORD }, env)
    ).resolves.toBe("ok");
    await expect(
      verifyAdminLogin({ username: "admin", password: "wrong" }, env)
    ).resolves.toBe("invalid");
    await expect(
      verifyAdminLogin({ username: "root", password: TEST_PASSWORD }, env)
    ).resolves.toBe("invalid");
  });

  it("세션 secret이 약하면 로그인 설정을 거부한다", async () => {
    const passwordHash = await hashAdminPasswordForEnv(TEST_PASSWORD, new Uint8Array(16).fill(2));

    await expect(
      verifyAdminLogin(
        { username: "admin", password: TEST_PASSWORD },
        {
          KTG_UI_ADMIN_PASSWORD_HASH: passwordHash,
          KTG_UI_SESSION_SECRET: "short"
        }
      )
    ).resolves.toBe("misconfigured");
  });

  it("세션 쿠키는 서명, 만료, user-agent fingerprint, 폐기를 검증한다", async () => {
    const env = await makeEnv(TEST_PASSWORD);
    const now = 1_800_000_000_000;
    const source = new Headers({ "user-agent": "unit-test-a" });
    const otherSource = new Headers({ "user-agent": "unit-test-b" });
    const value = await createSessionCookieValue(source, env, now);

    await expect(verifySessionCookieValue(value, env, now, source)).resolves.toBe(true);
    await expect(verifySessionCookieValue(value, env, now, otherSource)).resolves.toBe(false);
    await expect(
      verifySessionCookieValue(value, env, now + (SESSION_TTL_SECONDS + 61) * 1000, source)
    ).resolves.toBe(false);

    const revocable = await createSessionCookieValue(source, env, now);
    await revokeSessionCookieValue(revocable, env, now);
    await expect(verifySessionCookieValue(revocable, env, now, source)).resolves.toBe(false);
  });

  it("로그인 실패 횟수를 IP 기준으로 제한하고 성공 후 초기화할 수 있다", () => {
    const source = new Headers({ "x-forwarded-for": `198.51.100.${Date.now() % 255}` });

    expect(checkLoginRateLimit({ headers: source })).toEqual({ allowed: true });
    for (let i = 0; i < 5; i += 1) {
      recordLoginFailure({ headers: source });
    }
    expect(checkLoginRateLimit({ headers: source }).allowed).toBe(false);

    clearLoginFailures({ headers: source });
    expect(checkLoginRateLimit({ headers: source })).toEqual({ allowed: true });
  });

  it("next 경로는 로컬 경로만 허용한다", () => {
    expect(sanitizeLocalPath("/admin/settings")).toBe("/admin/settings");
    expect(sanitizeLocalPath("https://example.com/admin")).toBe("/debug/geocode");
    expect(sanitizeLocalPath("//example.com/admin")).toBe("/debug/geocode");
    expect(sanitizeLocalPath("/admin\\settings")).toBe("/debug/geocode");
  });
});

async function makeEnv(password: string): Promise<Record<string, string>> {
  return {
    KTG_UI_ADMIN_PASSWORD_HASH: await hashAdminPasswordForEnv(
      password,
      new Uint8Array(16).fill(1)
    ),
    KTG_UI_ADMIN_USERNAME: "admin",
    KTG_UI_SESSION_SECRET: SESSION_SECRET
  };
}
