import { recordUiRequest, recordWebVital } from "@/lib/metrics";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: Request) {
  const startedAt = performance.now();
  let statusCode = 204;
  try {
    const payload = (await request.json()) as {
      name?: unknown;
      route?: unknown;
      rating?: unknown;
      value?: unknown;
    };
    if (
      typeof payload.name === "string" &&
      typeof payload.route === "string" &&
      typeof payload.value === "number"
    ) {
      recordWebVital({
        name: payload.name,
        route: payload.route,
        rating: typeof payload.rating === "string" ? payload.rating : "unknown",
        value: payload.value
      });
    } else {
      statusCode = 400;
    }
  } catch {
    statusCode = 400;
  } finally {
    recordUiRequest({
      method: "POST",
      route: "/api/metrics/web-vitals",
      statusCode,
      elapsedSeconds: (performance.now() - startedAt) / 1_000
    });
  }
  return new Response(null, { status: statusCode });
}
