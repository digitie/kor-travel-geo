import { expect, test } from "@playwright/test";

import { proxyGet, proxyPost } from "./_live";

// Layer 4 — negative / edge cases exercised through the same-origin proxy
// against a LIVE backend (DB + API + UI). Gated behind LIVE_E2E.
//
// Verified LIVE error contract (V2ErrorEnvelope) for bad input:
//   HTTP 400 with body
//   { status: "ERROR", query_id: string,
//     error: { code: "E0100", message: "invalid request data", hint: string, field?: string } }

interface V2ErrorEnvelope {
  status: string;
  query_id: string;
  error: {
    code: string;
    message: string;
    hint: string;
    field?: string;
  };
}

interface V2GeocodeOk {
  status: string;
  query_id: string;
  candidates: unknown[];
}

test.describe("LIVE v2 negative / edge cases", () => {
  test.beforeEach(() => {
    test.skip(!process.env.LIVE_E2E, "Live full-stack test — run with LIVE_E2E=1 and the stack up (DB+API+UI)");
  });

  test("v2/geocode empty query → 400 E0100 invalid request data", async ({ request }) => {
    const res = await proxyPost(request, "v2/geocode", { query: "" });
    expect(res.status()).toBe(400);

    const body = (await res.json()) as V2ErrorEnvelope;
    expect(body.status).toBe("ERROR");
    expect(typeof body.query_id).toBe("string");
    expect(body.query_id.length).toBeGreaterThan(0);
    expect(body.error.code).toBe("E0100");
    expect(body.error.message).toBe("invalid request data");
    expect(body.error.hint).toContain("query");
  });

  test("v2/reverse missing lon/lat → 400 E0100 with field=lon", async ({ request }) => {
    const res = await proxyPost(request, "v2/reverse", {});
    expect(res.status()).toBe(400);

    const body = (await res.json()) as V2ErrorEnvelope;
    expect(body.status).toBe("ERROR");
    expect(typeof body.query_id).toBe("string");
    expect(body.query_id.length).toBeGreaterThan(0);
    expect(body.error.code).toBe("E0100");
    expect(body.error.hint).toContain("lon");
    expect(body.error.field).toBe("lon");
  });

  test("v2/search missing query → 400 E0100", async ({ request }) => {
    const res = await proxyPost(request, "v2/search", {});
    expect(res.status()).toBe(400);

    const body = (await res.json()) as V2ErrorEnvelope;
    expect(body.status).toBe("ERROR");
    expect(typeof body.query_id).toBe("string");
    expect(body.query_id.length).toBeGreaterThan(0);
    expect(body.error.code).toBe("E0100");
  });

  test("v2/geocode no-match → 200 status NOT_FOUND with no candidates", async ({ request }) => {
    const res = await proxyPost(request, "v2/geocode", {
      query: "존재하지않는엉터리주소zzqqxx9999"
    });
    // No-match is a successful HTTP response carrying status "NOT_FOUND" (not an error).
    expect(res.status()).toBe(200);

    const body = (await res.json()) as V2GeocodeOk;
    expect(body.status).toBe("NOT_FOUND");
    expect(typeof body.query_id).toBe("string");
    expect(body.query_id.length).toBeGreaterThan(0);
    expect((body.candidates ?? []).length).toBe(0);
  });

  test("v1/address/geocode missing required `address` → validation error (>=400)", async ({ request }) => {
    // vworld-compat surface: the `address` param is required, so omitting it
    // must fail validation rather than returning a 2xx.
    const res = await proxyGet(request, "v1/address/geocode");
    expect(res.ok()).toBe(false);
    expect(res.status()).toBeGreaterThanOrEqual(400);
  });
});
