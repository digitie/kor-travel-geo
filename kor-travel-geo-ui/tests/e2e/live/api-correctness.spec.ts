import { expect, test } from "@playwright/test";

import {
  KNOWN,
  expectInKorea,
  expectNearKnown,
  proxyGet,
  proxyPost
} from "./_live";

// Layer 1 — LIVE API happy-path correctness through the same-origin proxy.
//
// These hit a LIVE backend + DB via the UI proxy (/api/proxy/<path>) using the
// Playwright `request` fixture. Gated behind LIVE_E2E so the default (no-stack)
// run skips instead of failing.

type GeocodeV1 = {
  response: {
    status: string;
    result: { crs: string; point: { x: number; y: number } };
    x_extension: {
      source: string;
      confidence: number;
      bd_mgt_sn: string;
      zip_no: string;
      buld_nm: string;
    };
  };
};

type Candidate = {
  confidence: number;
  match_kind?: string;
  address?: { full?: string; road_address?: string; postal_code?: string; road_name?: string };
  point: { lon: number; lat: number };
  region?: { sig_cd?: string; sido?: string; sigungu?: string };
  source?: string;
  distance_m?: number;
  metadata?: { bd_mgt_sn?: string };
};

type CandidatesV2 = {
  status: string;
  query_id: string;
  candidates: Candidate[];
};

type RegionEntry = { code: string; name: string; relation?: string };

type WithinRadiusV2 = {
  status: string;
  center: { lon: number; lat: number };
  radius_km: number;
  sido: RegionEntry[];
  sigungu: RegionEntry[];
  emd: RegionEntry[];
};

test.describe("LIVE v1/v2 geocoding correctness", () => {
  test.beforeEach(() => {
    test.skip(!process.env.LIVE_E2E, "Live full-stack test — run with LIVE_E2E=1 and the stack up (DB+API+UI)");
  });

  test("v1 health + readiness probes return 200", async ({ request }) => {
    const health = await proxyGet(request, "v1/healthz");
    expect(health.status()).toBe(200);

    const ready = await proxyGet(request, "v1/readyz");
    expect(ready.status()).toBe(200);
  });

  test("v1 geocode resolves the known anchor with x_extension", async ({ request }) => {
    // Note: the v1 `type` param is NOT the internal label — passing type="ROAD" yields
    // a 400 INVALID_TYPE. The default already resolves road addresses (input.type=ROAD),
    // so we omit it here.
    const res = await proxyGet(request, "v1/address/geocode", {
      address: KNOWN.address
    });
    expect(res.status()).toBe(200);

    const body = (await res.json()) as GeocodeV1;
    expect(body.response.status).toBe("OK");

    const { point } = body.response.result;
    expectInKorea(point.x, point.y);
    expectNearKnown(point.x, point.y);

    const ext = body.response.x_extension;
    expect(ext.bd_mgt_sn).toBe(KNOWN.bdMgtSn);
    expect(ext.zip_no).toBe(KNOWN.postalCode);
  });

  test("v2 geocode returns a top candidate matching the known anchor", async ({ request }) => {
    const res = await proxyPost(request, "v2/geocode", { query: KNOWN.address });
    expect(res.status()).toBe(200);

    const body = (await res.json()) as CandidatesV2;
    expect(body.status).toBe("OK");
    expect(typeof body.query_id).toBe("string");
    expect(body.query_id.length).toBeGreaterThan(0);
    expect(body.candidates.length).toBeGreaterThan(0);

    const c0 = body.candidates[0];
    expect(c0.address?.full).toBe(KNOWN.address);
    expect(c0.address?.postal_code).toBe(KNOWN.postalCode);
    expectNearKnown(c0.point.lon, c0.point.lat);
    expect(c0.region?.sig_cd).toBe(KNOWN.sigCd);
    expect(c0.region?.sigungu).toBe(KNOWN.sigungu);
    expect(c0.source).toBe("local");
  });

  test("v2 reverse geocode returns nearby candidates in 중구", async ({ request }) => {
    const res = await proxyPost(request, "v2/reverse", { lon: KNOWN.lon, lat: KNOWN.lat });
    expect(res.status()).toBe(200);

    const body = (await res.json()) as CandidatesV2;
    expect(body.status).toBe("OK");
    expect(body.candidates.length).toBeGreaterThan(0);

    const c0 = body.candidates[0];
    expect(typeof c0.distance_m).toBe("number");
    expectInKorea(c0.point.lon, c0.point.lat);
    expect(body.candidates.some((c) => c.region?.sigungu === "중구")).toBe(true);
  });

  test("v2 search by road name returns 세종대로 matches", async ({ request }) => {
    const res = await proxyPost(request, "v2/search", { query: "세종대로" });
    expect(res.status()).toBe(200);

    const body = (await res.json()) as CandidatesV2;
    expect(body.status).toBe("OK");
    expect(body.candidates.length).toBeGreaterThan(0);
    expect(
      body.candidates.some(
        (c) => (c.address?.full ?? "").includes("세종대로") || c.address?.road_name === "세종대로"
      )
    ).toBe(true);

    const c0 = body.candidates[0];
    expectInKorea(c0.point.lon, c0.point.lat);
  });

  test("v2 regions within-radius includes 중구 (11140)", async ({ request }) => {
    const res = await proxyPost(request, "v2/regions/within-radius", {
      lon: KNOWN.lon,
      lat: KNOWN.lat,
      radius_km: 1
    });
    expect(res.status()).toBe(200);

    const body = (await res.json()) as WithinRadiusV2;
    expect(body.status).toBe("OK");
    expectNearKnown(body.center.lon, body.center.lat);
    expect(body.radius_km).toBe(1);
    expect(Array.isArray(body.sigungu)).toBe(true);
    expect(body.sigungu.some((r) => r.code === "11140")).toBe(true);

    const junggu = body.sigungu.find((r) => r.code === "11140");
    expect(junggu?.name).toBe("중구");
  });
});
