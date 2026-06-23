import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

// The route gates on a valid admin session (lib/auth) before proxying. Mock it as authenticated
// so these tests exercise the abort/499/500 seam rather than the 401 auth gate.
vi.mock("@/lib/auth", () => ({
  requestHasValidSession: vi.fn().mockResolvedValue(true),
  adminUsernameFromEnv: vi.fn().mockReturnValue("e2e-admin")
}));

// Mock the metrics sink but keep backendRouteForMetrics real (the handler uses it to label
// the upstream histogram). recordProxyUpstream/recordUiRequest become spies we can assert on.
vi.mock("@/lib/metrics", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/metrics")>();
  return {
    ...actual,
    recordProxyUpstream: vi.fn(),
    recordUiRequest: vi.fn()
  };
});

import { recordProxyUpstream, recordUiRequest } from "@/lib/metrics";
import { GET } from "@/app/api/proxy/[...path]/route";

const fetchMock = vi.fn();

function makeRequest(signal: AbortSignal): NextRequest {
  return {
    method: "GET",
    headers: new Headers({ accept: "application/json" }),
    body: null,
    signal,
    nextUrl: { search: "" }
  } as unknown as NextRequest;
}

const context = { params: Promise.resolve({ path: ["v1", "admin", "tables"] }) };

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  vi.mocked(recordProxyUpstream).mockClear();
  vi.mocked(recordUiRequest).mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("BFF proxy route handler", () => {
  it("정상 응답은 status를 그대로 전달하고 client signal을 upstream fetch로 넘긴다", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify([{ table_name: "t" }]), {
        status: 200,
        headers: { "content-type": "application/json" }
      })
    );
    const controller = new AbortController();

    const res = await GET(makeRequest(controller.signal), context);

    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ signal: controller.signal, cache: "no-store" })
    );
    expect(recordProxyUpstream).toHaveBeenCalledWith(
      expect.objectContaining({ statusCode: 200 })
    );
  });

  it("클라이언트 abort면 499로 매핑하고 upstream 메트릭에 499를 기록한다", async () => {
    const controller = new AbortController();
    controller.abort();
    // The forwarded signal aborts the upstream fetch, which rejects with AbortError.
    fetchMock.mockRejectedValue(new DOMException("The operation was aborted.", "AbortError"));

    const res = await GET(makeRequest(controller.signal), context);

    expect(res.status).toBe(499);
    expect(recordProxyUpstream).toHaveBeenCalledWith(
      expect.objectContaining({ statusCode: 499 })
    );
    expect(recordUiRequest).toHaveBeenCalledWith(
      expect.objectContaining({ statusCode: 499 })
    );
  });

  it("abort가 아닌 upstream 오류는 전파하고 메트릭에 500을 기록한다", async () => {
    const controller = new AbortController(); // never aborted
    fetchMock.mockRejectedValue(new Error("ECONNREFUSED"));

    await expect(GET(makeRequest(controller.signal), context)).rejects.toThrow("ECONNREFUSED");

    expect(recordProxyUpstream).toHaveBeenCalledWith(
      expect.objectContaining({ statusCode: 500 })
    );
    expect(recordUiRequest).toHaveBeenCalledWith(
      expect.objectContaining({ statusCode: 500 })
    );
  });
});
