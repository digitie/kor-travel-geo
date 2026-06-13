import { NextRequest } from "next/server";
import {
  backendRouteForMetrics,
  recordProxyUpstream,
  recordUiRequest
} from "@/lib/metrics";
import { buildProxyRequestInit, buildProxyTarget, forwardedProxyHeaders } from "@/lib/proxy";

const INTERNAL_BASE = process.env.KTG_API_INTERNAL_URL ?? "http://localhost:12201";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const startedAt = performance.now();
  let statusCode = 500;
  const params = await context.params;
  const target = buildProxyTarget(params.path, request.nextUrl.search, INTERNAL_BASE);
  try {
    if (target === null) {
      statusCode = 403;
      return new Response("Forbidden", { status: statusCode });
    }
    const upstreamStartedAt = performance.now();
    const backendRoute = backendRouteForMetrics(params.path);
    let upstreamStatusCode = 500;
    const response = await fetch(target, {
      cache: "no-store",
      ...buildProxyRequestInit(
        request.method,
        forwardedProxyHeaders(request.headers),
        request.body
      )
    })
      .then((upstreamResponse) => {
        upstreamStatusCode = upstreamResponse.status;
        return upstreamResponse;
      })
      .finally(() => {
        recordProxyUpstream({
          method: request.method,
          backendRoute,
          statusCode: upstreamStatusCode,
          elapsedSeconds: (performance.now() - upstreamStartedAt) / 1000
        });
      });
    statusCode = response.status;
    return new Response(response.body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json"
      }
    });
  } finally {
    recordUiRequest({
      method: request.method,
      route: "/api/proxy/[...path]",
      statusCode,
      elapsedSeconds: (performance.now() - startedAt) / 1000
    });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
