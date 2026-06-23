import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Shared helpers for the LIVE full-stack e2e suite (tests/e2e/live/*).
//
// These specs run a real browser/API client against a LIVE backend + DB (not the
// fixture-mocked `page.route` suite). They are GATED behind `LIVE_E2E=1` so the default
// `playwright test` run (no backend) skips them instead of failing.
//
// Run with the stack up (see docs/live-e2e.md):
//   LIVE_E2E=1 PLAYWRIGHT_BROWSER=chromium npx playwright test tests/e2e/live

/** Ground-truth anchor address resolved from the loaded nationwide dataset (서울시청). */
export const KNOWN = {
  address: "서울특별시 중구 세종대로 110",
  roadName: "세종대로",
  lon: 126.9777,
  lat: 37.5662,
  sigCd: "11140",
  bjdCd: "1114010300",
  sido: "서울특별시",
  sigungu: "중구",
  postalCode: "04524",
  bdMgtSn: "11140103200500100011000000",
  buildingName: "서울특별시청"
} as const;

/** Approximate bounding box of South Korea, for coordinate-sanity assertions. */
export const KR_BBOX = { lonMin: 124, lonMax: 132, latMin: 33, latMax: 43 } as const;
export const LIVE_TIMEOUT = 15_000;

export function expectInKorea(lon: unknown, lat: unknown): void {
  expect(typeof lon).toBe("number");
  expect(typeof lat).toBe("number");
  expect(lon as number).toBeGreaterThan(KR_BBOX.lonMin);
  expect(lon as number).toBeLessThan(KR_BBOX.lonMax);
  expect(lat as number).toBeGreaterThan(KR_BBOX.latMin);
  expect(lat as number).toBeLessThan(KR_BBOX.latMax);
}

/** Assert the resolved point is within ~`toleranceDeg` of the known anchor (default ~1.1km). */
export function expectNearKnown(lon: number, lat: number, toleranceDeg = 0.01): void {
  expect(Math.abs(lon - KNOWN.lon)).toBeLessThan(toleranceDeg);
  expect(Math.abs(lat - KNOWN.lat)).toBeLessThan(toleranceDeg);
}

/** GET through the same-origin proxy (`/api/proxy/<path>`) using the configured baseURL. */
export async function proxyGet(
  request: APIRequestContext,
  path: string,
  params?: Record<string, string | number | boolean>
) {
  const qs = params
    ? "?" +
      Object.entries(params)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
        .join("&")
    : "";
  return request.get(`/api/proxy/${path}${qs}`);
}

/** POST JSON through the same-origin proxy. */
export async function proxyPost(request: APIRequestContext, path: string, data: unknown) {
  return request.post(`/api/proxy/${path}`, { data });
}

export async function expectNoErrorScreen(page: Page): Promise<void> {
  await expect(page.getByText("This page couldn")).toHaveCount(0);
  await expect(page.getByText("이 화면을 불러오지 못했습니다")).toHaveCount(0);
}

// NOTE: the legacy KTG_LIVE_E2E_ADMIN_PROXY/ACTOR/ROLES opt-in (and its hasLiveAdminProxyRole
// gate) is retired — admin role injection now derives from the logged-in admin session
// (loginLiveAdmin), so role-gated reads run without that env trio. lib/proxy.ts still keeps
// liveE2EAdminIdentityFromEnv as a harmless fallback for the proxy.

export function isLiveE2EEnabled(): boolean {
  return Boolean(process.env.LIVE_E2E);
}

export function liveAdminCredentials(): { username: string; password: string } | null {
  const password = process.env.KTG_LIVE_E2E_ADMIN_PASSWORD?.trim();
  if (!password) {
    return null;
  }
  return {
    username: process.env.KTG_LIVE_E2E_ADMIN_USERNAME?.trim() || "admin",
    password
  };
}

export async function loginLiveAdmin(
  request: APIRequestContext,
  nextPath = "/debug/geocode"
): Promise<void> {
  const credentials = liveAdminCredentials();
  test.skip(
    credentials === null,
    "Live admin auth test — set KTG_LIVE_E2E_ADMIN_PASSWORD without committing it"
  );
  if (credentials === null) return;

  const response = await request.post("/api/auth/login", {
    data: {
      next: nextPath,
      password: credentials.password,
      username: credentials.username
    },
    headers: {
      "x-forwarded-for": "127.0.0.1"
    }
  });
  expect(response.status()).toBe(200);
  const setCookie = response.headers()["set-cookie"] ?? "";
  expect(setCookie).toContain("ktg_ui_session=");
  expect(setCookie.toLowerCase()).toContain("httponly");
  expect(setCookie.toLowerCase()).toContain("samesite=strict");
}

export async function loginLiveAdminPage(
  page: Page,
  nextPath = "/debug/geocode"
): Promise<void> {
  const credentials = liveAdminCredentials();
  test.skip(
    credentials === null,
    "Live admin auth test — set KTG_LIVE_E2E_ADMIN_PASSWORD without committing it"
  );
  if (credentials === null) return;

  const userAgent = await page.evaluate(() => navigator.userAgent);
  const response = await page.request.post("/api/auth/login", {
    data: {
      next: nextPath,
      password: credentials.password,
      username: credentials.username
    },
    headers: {
      "user-agent": userAgent,
      "x-forwarded-for": "127.0.0.1"
    }
  });
  expect(response.status()).toBe(200);
  const setCookie = response.headers()["set-cookie"] ?? "";
  expect(setCookie).toContain("ktg_ui_session=");
  expect(setCookie.toLowerCase()).toContain("httponly");
  expect(setCookie.toLowerCase()).toContain("samesite=strict");
}

export function liveApiBaseUrl(): string | null {
  const value = (process.env.KTG_LIVE_E2E_API_BASE_URL ?? process.env.KTG_API_INTERNAL_URL)?.trim();
  if (!value) {
    return null;
  }
  try {
    return new URL(value).toString();
  } catch {
    return null;
  }
}

export async function directApiGet(
  request: APIRequestContext,
  path: string,
  params?: Record<string, string | number | boolean>
) {
  const url = liveApiUrl(path, params);
  test.skip(
    url === null,
    "Direct live API test — set KTG_LIVE_E2E_API_BASE_URL or KTG_API_INTERNAL_URL"
  );
  if (url === null) throw new Error("direct live API base URL is not configured");
  return request.get(url);
}

export async function directApiPost(
  request: APIRequestContext,
  path: string,
  data: unknown,
  params?: Record<string, string | number | boolean>
) {
  const url = liveApiUrl(path, params);
  test.skip(
    url === null,
    "Direct live API test — set KTG_LIVE_E2E_API_BASE_URL or KTG_API_INTERNAL_URL"
  );
  if (url === null) throw new Error("direct live API base URL is not configured");
  return request.post(url, { data });
}

function liveApiUrl(
  path: string,
  params?: Record<string, string | number | boolean>
): string | null {
  const baseUrl = liveApiBaseUrl();
  if (baseUrl === null) {
    return null;
  }
  const url = new URL(path.startsWith("/") ? path : `/${path}`, baseUrl);
  for (const [key, value] of Object.entries(params ?? {})) {
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}
