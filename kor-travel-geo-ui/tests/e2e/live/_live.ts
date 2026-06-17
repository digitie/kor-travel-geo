import { expect, type APIRequestContext } from "@playwright/test";

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
