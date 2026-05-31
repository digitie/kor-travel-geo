import { NextRequest } from "next/server";
import { buildProxyRequestInit, buildProxyTarget, forwardedProxyHeaders } from "@/lib/proxy";

const INTERNAL_BASE = process.env.KRADDR_GEO_API_INTERNAL_URL ?? "http://localhost:8888";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const params = await context.params;
  const target = buildProxyTarget(params.path, request.nextUrl.search, INTERNAL_BASE);
  if (target === null) {
    return new Response("Forbidden", { status: 403 });
  }
  const response = await fetch(target, {
    ...buildProxyRequestInit(
      request.method,
      forwardedProxyHeaders(request.headers),
      request.body
    )
  });
  return new Response(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json"
    }
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
