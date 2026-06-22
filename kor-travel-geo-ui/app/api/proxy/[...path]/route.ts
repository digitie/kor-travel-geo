import { NextRequest } from "next/server";
import {
  backendRouteForMetrics,
  recordProxyUpstream,
  recordUiRequest
} from "@/lib/metrics";
import { buildProxyRequestInit, buildProxyTarget, forwardedProxyHeaders } from "@/lib/proxy";

const INTERNAL_BASE = process.env.KTG_API_INTERNAL_URL ?? "http://localhost:12501";

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
    try {
      const response = await fetch(target, {
        ...buildProxyRequestInit(
          request.method,
          forwardedProxyHeaders(request.headers),
          request.body,
          request.signal
        )
      });
      upstreamStatusCode = response.status;
      statusCode = response.status;
      return new Response(response.body, {
        status: response.status,
        headers: {
          "content-type": response.headers.get("content-type") ?? "application/json"
        }
      });
    } catch (error) {
      // Client aborted (navigation / react-query cancel): request.signal aborts
      // the upstream fetch above, freeing the connection. Surface 499 (client
      // closed request) instead of letting it look like a 500 backend failure.
      if (request.signal.aborted) {
        upstreamStatusCode = 499;
        statusCode = 499;
        return new Response(null, { status: 499 });
      }
      throw error;
    } finally {
      recordProxyUpstream({
        method: request.method,
        backendRoute,
        statusCode: upstreamStatusCode,
        elapsedSeconds: (performance.now() - upstreamStartedAt) / 1000
      });
    }
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
