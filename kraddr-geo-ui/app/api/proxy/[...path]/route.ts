import { NextRequest } from "next/server";

const INTERNAL_BASE = process.env.KRADDR_GEO_API_INTERNAL_URL ?? "http://localhost:8000";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const params = await context.params;
  const target = new URL(`/${params.path.join("/")}`, INTERNAL_BASE);
  target.search = request.nextUrl.search;
  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();
  const response = await fetch(target, {
    method: request.method,
    headers: forwardedHeaders(request),
    body,
    cache: "no-store"
  });
  return new Response(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json"
    }
  });
}

function forwardedHeaders(request: NextRequest): Headers {
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");
  return headers;
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
