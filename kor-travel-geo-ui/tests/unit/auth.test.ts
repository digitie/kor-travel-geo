import { afterEach, describe, expect, it, vi } from "vitest";

import {
  SESSION_TTL_SECONDS,
  checkDurableLoginRateLimit,
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
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

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

  it("아이디가 틀려도 PBKDF2를 수행해 username timing 차이를 줄인다", async () => {
    const env = await makeEnv(TEST_PASSWORD);
    const deriveBits = vi.spyOn(crypto.subtle, "deriveBits");

    await expect(
      verifyAdminLogin({ username: "root", password: TEST_PASSWORD }, env)
    ).resolves.toBe("invalid");

    expect(deriveBits).toHaveBeenCalled();
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

  it("audit 로그 기반 durable 로그인 제한을 적용한다", async () => {
    const now = 1_800_000_000_000;
    const clientIp = "203.0.113.42";
    const clientIpHash = await sha256Hex(clientIp);
    const rows = Array.from({ length: 5 }, (_, index) => ({
      client_ip_hash: clientIpHash,
      occurred_at: new Date(now - index * 1_000).toISOString(),
      outcome: "denied",
      payload_redacted: { reason: "invalid_credentials" }
    }));
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
      return new Response(JSON.stringify(rows), {
        headers: { "content-type": "application/json" },
        status: 200
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await checkDurableLoginRateLimit(
      { headers: new Headers({ "x-forwarded-for": clientIp }) },
      {
        KTG_ADMIN_PROXY_SECRET: "proxy-secret",
        KTG_API_INTERNAL_URL: "http://backend.internal",
        KTG_UI_TRUSTED_PROXY_HOPS: "1"
      },
      now
    );

    expect(result?.allowed).toBe(false);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [RequestInfo | URL, RequestInit];
    expect(String(url)).toContain("/v1/admin/ops/audit-events");
    expect((init?.headers as Headers).get("x-ktg-admin-proxy-secret")).toBe("proxy-secret");
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

async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}
