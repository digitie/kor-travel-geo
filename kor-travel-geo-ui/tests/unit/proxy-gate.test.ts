import { describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

const { requestHasValidSession } = vi.hoisted(() => ({
  requestHasValidSession: vi.fn().mockResolvedValue(false)
}));

vi.mock("@/lib/auth", () => ({
  requestHasValidSession,
  sanitizeLocalPath: (value: string | null) => value ?? "/admin"
}));

import { proxy } from "@/proxy";

function makeRequest(pathname: string, search = ""): NextRequest {
  return {
    nextUrl: { pathname, search, searchParams: new URLSearchParams(search) },
    url: `http://ui.test${pathname}${search}`,
    headers: new Headers()
  } as unknown as NextRequest;
}

describe("Next request auth gate", () => {
  it("Prometheus aggregate scrape path is public without opening Web Vitals ingestion", async () => {
    requestHasValidSession.mockClear();

    const response = await proxy(makeRequest("/api/metrics", "?scrape=1"));

    expect(response.status).toBe(200);
    expect(requestHasValidSession).not.toHaveBeenCalled();
  });

  it("keeps nested metrics paths behind the session gate", async () => {
    requestHasValidSession.mockClear();

    const response = await proxy(makeRequest("/api/metrics/web-vitals"));

    expect(response.status).toBe(401);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(requestHasValidSession).toHaveBeenCalledOnce();
  });
});
