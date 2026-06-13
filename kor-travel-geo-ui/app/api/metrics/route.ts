import { recordUiRequest, renderPrometheusMetrics } from "@/lib/metrics";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET() {
  const startedAt = performance.now();
  let statusCode = 500;
  try {
    const response = new Response(renderPrometheusMetrics(), {
      headers: {
        "content-type": "text/plain; version=0.0.4; charset=utf-8",
        "cache-control": "no-store"
      }
    });
    statusCode = response.status;
    return response;
  } finally {
    recordUiRequest({
      method: "GET",
      route: "/api/metrics",
      statusCode,
      elapsedSeconds: (performance.now() - startedAt) / 1_000
    });
  }
}
