import { expect, test, type APIResponse } from "@playwright/test";

import {
  KNOWN,
  expectInKorea,
  expectNearKnown,
  isLiveE2EEnabled,
  loginLiveAdmin,
  proxyGet,
  proxyPost
} from "./_live";

// Broad LIVE public API matrix.
//
// These cases intentionally stay read-only and go through the UI same-origin proxy, so they
// exercise Next proxy -> live FastAPI -> live PostgreSQL/PostGIS without mutating state.

type Row = Record<string, unknown>;

async function json<T = Row>(res: APIResponse): Promise<T> {
  return (await res.json()) as T;
}

function expectTrace(body: Row): void {
  expect(typeof body.query_id).toBe("string");
  expect(String(body.query_id).length).toBeGreaterThan(0);
}

function expectV2CandidateList(body: Row): void {
  expect(["OK", "NOT_FOUND"]).toContain(body.status);
  expectTrace(body);
  expect(Array.isArray(body.candidates)).toBe(true);
}

function expectV1Envelope(body: Row, operation: string): Row {
  expect(typeof body.response).toBe("object");
  const response = body.response as Row;
  expect(response.status).toBe("OK");
  expect(typeof response.service).toBe("object");
  expect((response.service as Row).operation).toBe(operation);
  return response;
}

test.describe("LIVE public API read-only matrix", () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdmin(request);
  });

  const v1GeocodeCases: Array<{ name: string; params: Record<string, string | number | boolean> }> = [
    { name: "known road default", params: { address: KNOWN.address } },
    { name: "known road explicit type", params: { address: KNOWN.address, type: "road" } },
    { name: "known road simple true", params: { address: KNOWN.address, simple: true } },
    { name: "known road refine false", params: { address: KNOWN.address, refine: false } },
    { name: "known road fallback off", params: { address: KNOWN.address, fallback: "off" } },
    { name: "known road local-only fallback", params: { address: KNOWN.address, fallback: "local_only" } },
    { name: "known road sig_cd hint", params: { address: KNOWN.address, sig_cd: KNOWN.sigCd } },
    { name: "known road bjd_cd hint", params: { address: KNOWN.address, bjd_cd: KNOWN.bjdCd } },
    { name: "known road crs explicit", params: { address: KNOWN.address, crs: "EPSG:4326" } },
    { name: "known road abbreviated", params: { address: "서울 중구 세종대로 110" } },
    { name: "known parcel default", params: { address: "서울특별시 중구 정동 5-5", type: "parcel" } },
    { name: "known road spaced", params: { address: "  서울특별시 중구 세종대로 110  " } }
  ];

  for (const item of v1GeocodeCases) {
    test(`v1/address/geocode ${item.name}`, async ({ request }) => {
      const res = await proxyGet(request, "v1/address/geocode", item.params);
      expect(res.status()).toBe(200);
      const response = expectV1Envelope(await json(res), "getCoord");
      const result = response.result as Row;
      const point = result.point as Row | undefined;
      if (point) {
        expectInKorea(point.x, point.y);
      }
    });
  }

  const v1ReverseCases: Array<{ name: string; params: Record<string, string | number | boolean> }> = [
    { name: "both default", params: { x: KNOWN.lon, y: KNOWN.lat } },
    { name: "road only", params: { x: KNOWN.lon, y: KNOWN.lat, type: "road" } },
    { name: "parcel only", params: { x: KNOWN.lon, y: KNOWN.lat, type: "parcel" } },
    { name: "zipcode false", params: { x: KNOWN.lon, y: KNOWN.lat, zipcode: false } },
    { name: "simple true", params: { x: KNOWN.lon, y: KNOWN.lat, simple: true } },
    { name: "radius 50m", params: { x: KNOWN.lon, y: KNOWN.lat, radius_m: 50 } },
    { name: "radius 200m", params: { x: KNOWN.lon, y: KNOWN.lat, radius_m: 200 } },
    { name: "sig_cd hint", params: { x: KNOWN.lon, y: KNOWN.lat, sig_cd: KNOWN.sigCd } },
    { name: "bjd_cd hint", params: { x: KNOWN.lon, y: KNOWN.lat, bjd_cd: KNOWN.bjdCd } },
    { name: "crs explicit", params: { x: KNOWN.lon, y: KNOWN.lat, crs: "EPSG:4326" } }
  ];

  for (const item of v1ReverseCases) {
    test(`v1/address/reverse ${item.name}`, async ({ request }) => {
      const res = await proxyGet(request, "v1/address/reverse", item.params);
      expect(res.status()).toBe(200);
      const response = expectV1Envelope(await json(res), "getAddress");
      expect(Array.isArray(response.result)).toBe(true);
      const rows = response.result as Row[];
      expect(rows.length).toBeGreaterThan(0);
      const point = rows[0].point as Row | undefined;
      if (point) {
        expectInKorea(point.x, point.y);
      }
    });
  }

  const v1SearchCases: Array<{ name: string; params: Record<string, string | number | boolean> }> = [
    { name: "road query size 1", params: { query: "세종대로", type: "road", size: 1 } },
    { name: "road query size 5", params: { query: "세종대로", type: "road", size: 5 } },
    { name: "road query page 2", params: { query: "세종대로", type: "road", page: 2, size: 3 } },
    { name: "address query", params: { query: KNOWN.address, type: "address", size: 3 } },
    { name: "district query", params: { query: "중구", type: "district", size: 5 } },
    { name: "place query", params: { query: KNOWN.buildingName, type: "place", size: 5 } },
    { name: "sig_cd hint", params: { query: "세종대로", sig_cd: KNOWN.sigCd, size: 5 } },
    { name: "bjd_cd hint", params: { query: "세종대로", bjd_cd: KNOWN.bjdCd, size: 5 } },
    { name: "short page", params: { query: "세종대로", page: 1, size: 2 } },
    { name: "no match", params: { query: "존재하지않는엉터리주소zzqqxx9999", size: 3 } }
  ];

  for (const item of v1SearchCases) {
    test(`v1/address/search ${item.name}`, async ({ request }) => {
      const res = await proxyGet(request, "v1/address/search", item.params);
      expect(res.status()).toBe(200);
      const body = await json(res);
      expect(["OK", "NOT_FOUND"]).toContain(body.status);
      expect(typeof body.service).toBe("object");
      expect(Array.isArray(body.result)).toBe(true);
      expect(typeof body.total).toBe("number");
    });
  }

  const v1ZipcodeCases: Array<{ name: string; params: Record<string, string | number | boolean> }> = [
    { name: "known address", params: { address: KNOWN.address } },
    { name: "known address no bulk", params: { address: KNOWN.address, include_bulk: false } },
    { name: "known point", params: { x: KNOWN.lon, y: KNOWN.lat } },
    { name: "known point no bulk", params: { x: KNOWN.lon, y: KNOWN.lat, include_bulk: false } }
  ];

  for (const item of v1ZipcodeCases) {
    test(`v1/address/zipcode ${item.name}`, async ({ request }) => {
      const res = await proxyGet(request, "v1/address/zipcode", item.params);
      expect(res.status()).toBe(200);
      const body = await json(res);
      expect(["OK", "NOT_FOUND"]).toContain(body.status);
      expect(Array.isArray(body.result)).toBe(true);
      if ((body.result as Row[]).length > 0) {
        expect(typeof (body.result as Row[])[0].zip_no).toBe("string");
      }
    });
  }

  const v1PoboxCases: Array<{ name: string; params: Record<string, string | number | boolean> }> = [
    { name: "query all", params: { query: "서울", kind: "ALL", size: 2 } },
    { name: "query PO", params: { query: "서울", kind: "PO", size: 2 } },
    { name: "query PG", params: { query: "서울", kind: "PG", size: 2 } },
    { name: "region fields", params: { si_nm: "서울특별시", sgg_nm: "중구", size: 2 } }
  ];

  for (const item of v1PoboxCases) {
    test(`v1/address/pobox ${item.name}`, async ({ request }) => {
      const res = await proxyGet(request, "v1/address/pobox", item.params);
      expect(res.status()).toBe(200);
      const body = await json(res);
      expect(["OK", "NOT_FOUND"]).toContain(body.status);
      expect(Array.isArray(body.result)).toBe(true);
      expect(typeof body.total).toBe("number");
    });
  }

  const v2GeocodeCases: Array<{ name: string; body: Row; expectKnown?: boolean }> = [
    { name: "query limit 1", body: { query: KNOWN.address, limit: 1 }, expectKnown: true },
    { name: "road_address", body: { road_address: KNOWN.address, limit: 1 }, expectKnown: true },
    { name: "keyword", body: { keyword: "세종대로", limit: 3 } },
    { name: "sig_cd hint", body: { query: KNOWN.address, sig_cd: KNOWN.sigCd, limit: 1 }, expectKnown: true },
    { name: "bjd_cd hint", body: { query: KNOWN.address, bjd_cd: KNOWN.bjdCd, limit: 1 }, expectKnown: true },
    {
      name: "bbox around Seoul",
      body: { query: KNOWN.address, bbox: { min_lon: 126.9, min_lat: 37.5, max_lon: 127.1, max_lat: 37.6 }, limit: 3 },
      expectKnown: true
    },
    { name: "include geometry", body: { query: KNOWN.address, include_geometry: true, limit: 1 }, expectKnown: true },
    { name: "fallback none explicit", body: { query: KNOWN.address, fallback: "none", limit: 1 }, expectKnown: true },
    { name: "limit 3", body: { query: KNOWN.address, limit: 3 }, expectKnown: true },
    { name: "abbreviated address", body: { query: "서울 중구 세종대로 110", limit: 3 } },
    { name: "road with spaces", body: { query: "  서울특별시 중구 세종대로 110  ", limit: 3 } },
    { name: "no match", body: { query: "존재하지않는엉터리주소zzqqxx9999", limit: 3 } }
  ];

  for (const item of v2GeocodeCases) {
    test(`v2/geocode ${item.name}`, async ({ request }) => {
      const res = await proxyPost(request, "v2/geocode", item.body);
      expect(res.status()).toBe(200);
      const body = await json(res);
      expectV2CandidateList(body);
      if (item.expectKnown) {
        const candidate = (body.candidates as Row[])[0];
        expect(candidate).toBeTruthy();
        const point = candidate.point as Row;
        expectNearKnown(point.lon as number, point.lat as number);
      }
    });
  }

  const v2ReverseCases: Array<{ name: string; body: Row }> = [
    { name: "default", body: { lon: KNOWN.lon, lat: KNOWN.lat } },
    { name: "include_region false", body: { lon: KNOWN.lon, lat: KNOWN.lat, include_region: false } },
    { name: "include_zipcode false", body: { lon: KNOWN.lon, lat: KNOWN.lat, include_zipcode: false } },
    { name: "radius 50", body: { lon: KNOWN.lon, lat: KNOWN.lat, radius_m: 50 } },
    { name: "radius 100", body: { lon: KNOWN.lon, lat: KNOWN.lat, radius_m: 100 } },
    { name: "radius 1000", body: { lon: KNOWN.lon, lat: KNOWN.lat, radius_m: 1000 } },
    { name: "sig_cd hint", body: { lon: KNOWN.lon, lat: KNOWN.lat, sig_cd: KNOWN.sigCd } },
    { name: "bjd_cd hint", body: { lon: KNOWN.lon, lat: KNOWN.lat, bjd_cd: KNOWN.bjdCd } },
    { name: "include geometry", body: { lon: KNOWN.lon, lat: KNOWN.lat, include_geometry: true, radius_m: 50 } },
    { name: "nearby offset", body: { lon: KNOWN.lon + 0.001, lat: KNOWN.lat + 0.001, radius_m: 500 } }
  ];

  for (const item of v2ReverseCases) {
    test(`v2/reverse ${item.name}`, async ({ request }) => {
      const res = await proxyPost(request, "v2/reverse", item.body);
      expect(res.status()).toBe(200);
      const body = await json(res);
      expectV2CandidateList(body);
      expect((body.candidates as Row[]).length).toBeGreaterThan(0);
    });
  }

  const v2SearchCases: Array<{ name: string; body: Row }> = [
    { name: "address known", body: { query: KNOWN.address, type: "address", size: 3 } },
    { name: "road known", body: { query: "세종대로", type: "road", size: 3 } },
    { name: "district", body: { query: "중구", type: "district", size: 5 } },
    { name: "place", body: { query: KNOWN.buildingName, type: "place", size: 5 } },
    { name: "sig_cd hint", body: { query: "세종대로", sig_cd: KNOWN.sigCd, size: 5 } },
    { name: "bjd_cd hint", body: { query: "세종대로", bjd_cd: KNOWN.bjdCd, size: 5 } },
    { name: "bbox around Seoul", body: { query: "세종대로", bbox: { min_lon: 126.9, min_lat: 37.5, max_lon: 127.1, max_lat: 37.6 }, size: 5 } },
    { name: "page 2", body: { query: "세종대로", type: "road", page: 2, size: 3 } },
    { name: "include geometry", body: { query: "세종대로", type: "road", include_geometry: true, size: 2 } },
    { name: "no match", body: { query: "존재하지않는엉터리주소zzqqxx9999", size: 3 } }
  ];

  for (const item of v2SearchCases) {
    test(`v2/search ${item.name}`, async ({ request }) => {
      const res = await proxyPost(request, "v2/search", item.body);
      expect(res.status()).toBe(200);
      const body = await json(res);
      expectV2CandidateList(body);
      expect(typeof body.total).toBe("number");
    });
  }

  const withinRadiusCases: Array<{ name: string; body: Row; field: "sido" | "sigungu" | "emd" }> = [
    { name: "sigungu 1km", body: { lon: KNOWN.lon, lat: KNOWN.lat, radius_km: 1, levels: ["sigungu"] }, field: "sigungu" },
    { name: "emd 1km", body: { lon: KNOWN.lon, lat: KNOWN.lat, radius_km: 1, levels: ["emd"] }, field: "emd" },
    { name: "sido 1km", body: { lon: KNOWN.lon, lat: KNOWN.lat, radius_km: 1, levels: ["sido"] }, field: "sido" },
    { name: "sigungu 5km", body: { lon: KNOWN.lon, lat: KNOWN.lat, radius_km: 5, levels: ["sigungu"] }, field: "sigungu" },
    { name: "dedupe levels", body: { lon: KNOWN.lon, lat: KNOWN.lat, radius_km: 1, levels: ["sigungu", "sigungu", "emd"] }, field: "sigungu" },
    { name: "default levels", body: { lon: KNOWN.lon, lat: KNOWN.lat, radius_km: 1 }, field: "sigungu" }
  ];

  for (const item of withinRadiusCases) {
    test(`v2/regions/within-radius ${item.name}`, async ({ request }) => {
      const res = await proxyPost(request, "v2/regions/within-radius", item.body);
      expect(res.status()).toBe(200);
      const body = await json(res);
      expect(body.status).toBe("OK");
      expectTrace(body);
      expect(Array.isArray(body[item.field])).toBe(true);
    });
  }
});

test.describe("LIVE public API validation matrix", () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!isLiveE2EEnabled(), "Live full-stack test — run with LIVE_E2E=1 and the stack up");
    await loginLiveAdmin(request);
  });

  const v2BadRequests: Array<{ name: string; path: string; body: Row; field?: string }> = [
    { name: "geocode missing lookup", path: "v2/geocode", body: {}, field: undefined },
    { name: "geocode limit zero", path: "v2/geocode", body: { query: KNOWN.address, limit: 0 }, field: "limit" },
    { name: "geocode bad sig_cd", path: "v2/geocode", body: { query: KNOWN.address, sig_cd: "abc" }, field: "sig_cd" },
    { name: "geocode bad bbox", path: "v2/geocode", body: { query: KNOWN.address, bbox: { min_lon: 127, min_lat: 37.6, max_lon: 126, max_lat: 37.5 } }, field: undefined },
    { name: "reverse outside Korea", path: "v2/reverse", body: { lon: 10, lat: 10 }, field: undefined },
    { name: "reverse radius zero", path: "v2/reverse", body: { lon: KNOWN.lon, lat: KNOWN.lat, radius_m: 0 }, field: "radius_m" },
    { name: "search page zero", path: "v2/search", body: { query: "세종대로", page: 0 }, field: "page" },
    { name: "search bad type", path: "v2/search", body: { query: "세종대로", type: "bad" }, field: "type" },
    { name: "radius empty levels", path: "v2/regions/within-radius", body: { lon: KNOWN.lon, lat: KNOWN.lat, levels: [] }, field: undefined },
    { name: "radius negative radius", path: "v2/regions/within-radius", body: { lon: KNOWN.lon, lat: KNOWN.lat, radius_km: -1 }, field: "radius_km" }
  ];

  for (const item of v2BadRequests) {
    test(`v2 validation ${item.name}`, async ({ request }) => {
      const res = await proxyPost(request, item.path, item.body);
      expect(res.status()).toBe(400);
      const body = await json(res);
      expect(body.status).toBe("ERROR");
      expectTrace(body);
      expect(typeof (body.error as Row).code).toBe("string");
      if (item.field) {
        expect(String((body.error as Row).hint ?? "")).toContain(item.field);
      }
    });
  }

  const v1BadRequests: Array<{ name: string; path: string; params?: Record<string, string | number | boolean> }> = [
    { name: "geocode bad type rejected", path: "v1/address/geocode", params: { address: KNOWN.address, type: "not-a-type" } },
    { name: "geocode bad sig_cd", path: "v1/address/geocode", params: { address: KNOWN.address, sig_cd: "abc" } },
    { name: "reverse missing x", path: "v1/address/reverse", params: { y: KNOWN.lat } },
    { name: "reverse bad type", path: "v1/address/reverse", params: { x: KNOWN.lon, y: KNOWN.lat, type: "bad" } },
    { name: "search missing query", path: "v1/address/search" },
    { name: "zipcode no lookup key", path: "v1/address/zipcode" }
  ];

  for (const item of v1BadRequests) {
    test(`v1 validation ${item.name}`, async ({ request }) => {
      const res = await proxyGet(request, item.path, item.params);
      // Must be a 4xx client error, not a 5xx server fault. `>= 400` alone would let a
      // 500/503 regression on a malformed-input path pass as long as the body still carried
      // status ERROR; the v2 sibling matrix pins toBe(400), so keep v1 in the client range too.
      const status = res.status();
      expect(status).toBeGreaterThanOrEqual(400);
      expect(status).toBeLessThan(500);
      const body = await json(res);
      expect(typeof body.response).toBe("object");
      expect((body.response as Row).status).toBe("ERROR");
    });
  }
});
